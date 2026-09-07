"""The same durable dispatch path serves browser confirmations and authorized jobs."""

from fastapi import HTTPException
from sqlalchemy import select

from .access import owned
from .email_drafts import attachments, draft_view
from .graph_email import send_email
from .models import ChatTurn, Conversation, EmailAttempt, EmailDraft, new_id, now
from .runtime import RuntimeFailure


def dispatch_email(
    factory,
    microsoft,
    organization_id,
    authorize,
    draft_id,
    version,
    *,
    initiator="browser",
    autonomy_version=None,
    check_draft=None,
    authorize_result=None,
):
    with factory.begin() as db:
        user = authorize(db)
        draft = owned(db, EmailDraft, organization_id, user.id, draft_id)
        if check_draft:
            check_draft(db, draft)
        previous = db.scalar(
            select(EmailAttempt).where(
                EmailAttempt.draft_id == draft_id,
                EmailAttempt.version == version,
            )
        )
        if previous:
            return draft_view(db, draft)
        if draft.version != version:
            raise HTTPException(409, "email_draft_changed")
        if not draft_view(db, draft)["editable"]:
            raise HTTPException(409, "email_draft_locked")
        files = [
            (item.filename, item.media_type, item.content)
            for item in attachments(db, organization_id, user.id, draft.message)
        ]
        message = draft.message
        turn = db.get(ChatTurn, draft.turn_id)
        provider = db.get(Conversation, turn.conversation_id).integration_provider
        attempt = EmailAttempt(
            organization_id=organization_id,
            owner_id=user.id,
            draft_id=draft.id,
            version=draft.version,
            message=message,
            correlation_id=new_id(),
            initiator=initiator,
            autonomy_version=autonomy_version,
        )
        db.add(attempt)
        db.flush()
        attempt_id, correlation_id = attempt.id, attempt.correlation_id
    # Commit before dispatch: lost replies or crashes never reset this version.
    try:
        if provider == "infomaniak":
            from .infomaniak import InfomaniakReader

            InfomaniakReader(microsoft.settings, factory).send(
                organization_id, authorize, message, files, correlation_id
            )
        else:
            microsoft.execute(
                organization_id,
                authorize,
                "mail_send",
                lambda graph, token: send_email(graph, token, message, files, correlation_id),
            )
        status, error = "accepted", None
    except HTTPException as failure:
        error = str(failure.detail)
        status = "unknown" if error == "email_send_unknown" else "failed"
    except RuntimeFailure as failure:
        # A cancelled/expired job is rejected by authorize before Graph dispatch.
        status, error = "failed", str(failure)
    with factory.begin() as db:
        attempt = db.get(EmailAttempt, attempt_id)
        attempt.status, attempt.error_code, attempt.finished_at = status, error, now()
    with factory.begin() as db:
        user = (authorize_result or authorize)(db)
        return draft_view(db, owned(db, EmailDraft, organization_id, user.id, draft_id))
