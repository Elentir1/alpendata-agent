"""Versioned browser reviews and durable e-mail submission receipts."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field

from .access import owned
from .auth import authenticate, request_authorization
from .connections import MicrosoftReader, lock_member
from .email_dispatch import dispatch_email
from .email_drafts import MessageInput, attachments, draft_view
from .email_verification import verify_attempt
from .models import EmailDraft, now
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
        return dispatch_email(
            factory,
            microsoft,
            organization_id,
            lambda db: actor(db, request, organization_id),
            draft_id,
            body.version,
            authorize_result=lambda db: actor(db, request, organization_id, licensed=False),
        )

    @router.post(path + "/attempts/{attempt_id}/verify")
    def verify(organization_id: str, draft_id: str, attempt_id: str, request: Request):
        return verify_attempt(factory, microsoft, actor, request, organization_id, draft_id, attempt_id)

    return router
