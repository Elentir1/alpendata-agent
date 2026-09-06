"""Job-scoped authorization for the optional email dispatch tool."""

from uuid import UUID

from fastapi import HTTPException
from pydantic import Field
from sqlalchemy import select

from .action_policy import require_email_autonomy
from .email_dispatch import dispatch_email
from .models import ChatTurn, Conversation, EmailAttempt, EmailDraft
from .routine_delivery import check_delivery_draft
from .schemas import Input


class SendInput(Input):
    draft_id: UUID
    version: int = Field(ge=1)


def send_agent_email(factory, microsoft, authorize_job, job, payload):
    body = SendInput.model_validate(payload)
    with factory.begin() as db:
        authorize_job(db, job)
        turn = db.get(ChatTurn, job.id)
        conversation = db.get(Conversation, turn.conversation_id)
        if not conversation.email_send_enabled or conversation.tool_revision < 4:
            raise HTTPException(403, "email_new_conversation_required")
        if conversation.purpose != "chat" and conversation.email_delivery is None:
            raise HTTPException(403, "routine_email_not_available")
        version = require_email_autonomy(db, job.organization_id, job.owner_id)

    def authorize(db):
        user = authorize_job(db, job)
        require_email_autonomy(db, job.organization_id, job.owner_id, version)
        return user

    def check_draft(db, draft):
        check_delivery_draft(db, db.get(ChatTurn, job.id), draft)
        if draft.turn_id != job.id:
            raise HTTPException(403, "email_draft_wrong_turn")
        unresolved = db.scalar(
            select(EmailAttempt.id)
            .join(EmailDraft, EmailDraft.id == EmailAttempt.draft_id)
            .where(
                EmailDraft.turn_id == job.id,
                EmailDraft.id != draft.id,
                EmailAttempt.status.in_(("sending", "unknown")),
            )
            .limit(1)
        )
        if unresolved:
            raise HTTPException(409, "email_send_unresolved")

    return dispatch_email(
        factory,
        microsoft,
        job.organization_id,
        authorize,
        str(body.draft_id),
        body.version,
        initiator="agent",
        autonomy_version=version,
        check_draft=check_draft,
        authorize_result=lambda db: authorize_job(db, job),
    )
