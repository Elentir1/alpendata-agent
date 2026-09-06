"""Versioned browser reviews and durable e-mail submission receipts."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field
from sqlalchemy import select

from .access import owned
from .auth import authenticate, request_authorization
from .connections import MicrosoftReader, lock_member
from .email_drafts import MessageInput, attachments, draft_view
from .email_verification import verify_attempt
from .graph_email import send_email
from .models import EmailAttempt, EmailDraft, new_id, now
from .schemas import Input


class EditInput(Input):
    version: int = Field(ge=1)
    message: MessageInput


class SendInput(Input):
    version: int = Field(ge=1)
    confirmed: Literal[True]


def email_router(settings, factory, provider=None, graph=None):
    router = APIRouter()
    microsoft = MicrosoftReader(settings, factory, provider, graph)
    path = "/api/organizations/{organization_id}/emails/{draft_id}"

    def actor(db, request, organization_id, *, licensed=True):
        user = authenticate(db, request_authorization(request, settings))
        lock_member(db, user, organization_id, licensed=licensed)
        return user

    @router.get(path)
    def read(organization_id: str, draft_id: str, request: Request):
        with factory.begin() as db:
            user = actor(db, request, organization_id, licensed=False)
            return draft_view(db, owned(db, EmailDraft, organization_id, user.id, draft_id))

    @router.patch(path)
    def edit(organization_id: str, draft_id: str, request: Request, body: EditInput):
        with factory.begin() as db:
            user = actor(db, request, organization_id)
            draft = owned(db, EmailDraft, organization_id, user.id, draft_id)
            if draft.version != body.version:
                raise HTTPException(409, "email_draft_changed")
            if not draft_view(db, draft)["editable"]:
                raise HTTPException(409, "email_draft_locked")
            message = body.message.model_dump(mode="json")
            attachments(db, organization_id, user.id, message)
            # Saving after a known rejection creates a new explicit review version.
            draft.message, draft.version, draft.updated_at = message, draft.version + 1, now()
            db.flush()
            return draft_view(db, draft)

    @router.post(path + "/send")
    def send(organization_id: str, draft_id: str, request: Request, body: SendInput):
        with factory.begin() as db:
            user = actor(db, request, organization_id)
            draft = owned(db, EmailDraft, organization_id, user.id, draft_id)
            previous = db.scalar(
                select(EmailAttempt).where(
                    EmailAttempt.draft_id == draft_id, EmailAttempt.version == body.version
                )
            )
            if previous:
                return draft_view(db, draft)
            if draft.version != body.version:
                raise HTTPException(409, "email_draft_changed")
            if not draft_view(db, draft)["editable"]:
                raise HTTPException(409, "email_draft_locked")
            files = [
                (item.filename, item.media_type, item.content)
                for item in attachments(db, organization_id, user.id, draft.message)
            ]
            message = draft.message
            attempt = EmailAttempt(
                organization_id=organization_id,
                owner_id=user.id,
                draft_id=draft.id,
                version=draft.version,
                message=message,
                correlation_id=new_id(),
            )
            db.add(attempt)
            db.flush()
            attempt_id = attempt.id
            correlation_id = attempt.correlation_id
        # Commit BEFORE dispatch. Repeated confirmations only read this receipt.
        try:
            microsoft.execute(
                organization_id,
                lambda db: actor(db, request, organization_id),
                "mail_send",
                lambda graph, token: send_email(graph, token, message, files, correlation_id),
            )
            status, error = "accepted", None
        except HTTPException as failure:
            error = str(failure.detail)
            status = "unknown" if error == "email_send_unknown" else "failed"
        with factory.begin() as db:
            attempt = db.get(EmailAttempt, attempt_id)
            attempt.status, attempt.error_code, attempt.finished_at = status, error, now()
        with factory.begin() as db:
            user = actor(db, request, organization_id, licensed=False)
            return draft_view(db, owned(db, EmailDraft, organization_id, user.id, draft_id))

    @router.post(path + "/attempts/{attempt_id}/verify")
    def verify(organization_id: str, draft_id: str, attempt_id: str, request: Request):
        return verify_attempt(factory, microsoft, actor, request, organization_id, draft_id, attempt_id)

    return router
