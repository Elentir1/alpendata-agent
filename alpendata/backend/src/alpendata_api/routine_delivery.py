"""A reviewed recurring email has a fixed envelope and one dispatch per occurrence."""

from collections import Counter

from fastapi import HTTPException
from pydantic import Field, field_validator
from sqlalchemy import or_, select

from .email_drafts import MessageInput
from .models import Conversation, EmailAttempt, EmailDraft
from .schemas import Input


class DeliveryInput(Input):
    to: list[str] = Field(min_length=1, max_length=20)
    subject: str = Field(min_length=1, max_length=998)

    @field_validator("to")
    @classmethod
    def addresses(cls, values):
        return MessageInput.addresses(values)

    @field_validator("subject")
    @classmethod
    def subject_line(cls, value):
        return MessageInput.subject_line(value)


def matches_delivery(message, delivery):
    return (
        Counter(address.casefold() for address in message["to"])
        == Counter(address.casefold() for address in delivery["to"])
        and message["subject"] == delivery["subject"]
        and not message.get("cc")
        and not message.get("bcc")
        and not message.get("attachment_ids")
    )


def check_delivery_draft(db, turn, draft):
    from .routine_service import read_evidence

    conversation = db.get(Conversation, turn.conversation_id)
    delivery = conversation.email_delivery
    if delivery is None:
        return
    if not matches_delivery(draft.message, delivery):
        raise HTTPException(409, "routine_email_envelope_changed")
    if not set(conversation.capabilities) <= read_evidence(db, turn)[0]:
        raise HTTPException(409, "routine_sources_missing")
    other = db.scalar(
        select(EmailAttempt.id)
        .join(EmailDraft, EmailDraft.id == EmailAttempt.draft_id)
        .where(
            EmailDraft.turn_id == turn.id,
            or_(EmailAttempt.draft_id != draft.id, EmailAttempt.version != draft.version),
        )
        .limit(1)
    )
    if other:
        raise HTTPException(409, "routine_email_already_attempted")


def delivery_accepted(db, turn):
    delivery = db.get(Conversation, turn.conversation_id).email_delivery
    if delivery is None:
        return True
    attempts = db.scalars(
        select(EmailAttempt)
        .join(EmailDraft, EmailDraft.id == EmailAttempt.draft_id)
        .where(EmailDraft.turn_id == turn.id)
    ).all()
    return bool(
        len(attempts) == 1
        and attempts[0].status == "accepted"
        and attempts[0].initiator == "agent"
        and matches_delivery(attempts[0].message, delivery)
    )
