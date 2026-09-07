"""Private message preparation; a model tool never authorizes dispatch."""

import hashlib
import json
from uuid import UUID

from email_validator import validate_email
from fastapi import HTTPException
from pydantic import Field, field_validator, model_validator
from sqlalchemy import func, select

from .access import owned
from .models import Artifact, ChatTurn, Conversation, EmailAttempt, EmailDraft, now
from .schemas import Input


class MessageInput(Input):
    to: list[str] = Field(min_length=1, max_length=20)
    cc: list[str] = Field(default_factory=list, max_length=20)
    bcc: list[str] = Field(default_factory=list, max_length=20)
    subject: str = Field(min_length=1, max_length=998)
    body: str = Field(min_length=1, max_length=32000)
    attachment_ids: list[UUID] = Field(default_factory=list, max_length=5)

    @field_validator("to", "cc", "bcc")
    @classmethod
    def addresses(cls, values):
        return [
            validate_email(value, check_deliverability=False, allow_smtputf8=False).normalized
            for value in values
        ]

    @field_validator("subject")
    @classmethod
    def subject_line(cls, value):
        if not value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("Use a nonempty single line subject")
        return value

    @model_validator(mode="after")
    def limits(self):
        if len(self.to + self.cc + self.bcc) > 20:
            raise ValueError("At most twenty recipients")
        if len(set(self.attachment_ids)) != len(self.attachment_ids):
            raise ValueError("Duplicate attachments")
        return self


def attachments(db, organization_id, owner_id, message):
    files = [owned(db, Artifact, organization_id, owner_id, key) for key in message["attachment_ids"]]
    # Base64 plus JSON must fit the simple Graph sendMail request.
    if sum(item.size for item in files) > 2 * 1024 * 1024:
        raise HTTPException(413, "email_attachments_too_large")
    return files


def attempt_view(item):
    status = "unknown" if item.status == "sending" and item.created_at + 180 < now() else item.status
    return {
        "id": item.id,
        "version": item.version,
        "status": status,
        "error_code": item.error_code,
        "created_at": item.created_at,
        "finished_at": item.finished_at,
        "can_verify": bool(item.correlation_id) and status in ("unknown", "accepted"),
        "verification": item.verification,
        "initiator": item.initiator,
        "autonomy_version": item.autonomy_version,
    }


def draft_view(db, draft):
    turn = db.get(ChatTurn, draft.turn_id)
    provider = db.get(Conversation, turn.conversation_id).integration_provider
    attempts = db.scalars(
        select(EmailAttempt).where(EmailAttempt.draft_id == draft.id).order_by(EmailAttempt.version)
    ).all()
    return {
        "id": draft.id,
        "version": draft.version,
        "message": draft.message,
        "editable": not any(item.status != "failed" for item in attempts),
        "attachments": [
            {"id": item.id, "filename": item.filename, "size": item.size}
            for item in attachments(db, draft.organization_id, draft.owner_id, draft.message)
        ],
        "provider": provider,
        "attempts": [
            {**attempt_view(item), **({"can_verify": False} if provider == "infomaniak" else {})}
            for item in attempts
        ],
        "updated_at": draft.updated_at,
    }


def turn_emails(db, turn):
    return [
        draft_view(db, item)
        for item in db.scalars(
            select(EmailDraft).where(EmailDraft.turn_id == turn.id).order_by(EmailDraft.id)
        )
    ]


def prepare_email(db, turn, payload):
    message = MessageInput.model_validate(payload).model_dump(mode="json")
    digest = hashlib.sha256(json.dumps(message, sort_keys=True).encode()).hexdigest()
    previous = db.scalar(
        select(EmailDraft).where(EmailDraft.turn_id == turn.id, EmailDraft.initial_hash == digest)
    )
    if previous:
        return draft_view(db, previous)
    count = db.scalar(select(func.count()).select_from(EmailDraft).where(EmailDraft.turn_id == turn.id))
    if count >= 10:
        raise HTTPException(409, "email_draft_limit")
    attachments(db, turn.organization_id, turn.owner_id, message)
    draft = EmailDraft(
        organization_id=turn.organization_id,
        owner_id=turn.owner_id,
        turn_id=turn.id,
        initial_hash=digest,
        message=message,
    )
    db.add(draft)
    db.flush()
    return draft_view(db, draft)
