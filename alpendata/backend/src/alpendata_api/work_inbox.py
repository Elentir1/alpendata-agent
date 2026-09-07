"""One private inbox for completed work, pending reviews and interrupted executions."""

from fastapi import APIRouter, Query, Request
from sqlalchemy import func, select

from .access import member, owned
from .auth import authenticate, request_authorization
from .models import CalendarAction, ChatTurn, Conversation, EmailAttempt, EmailDraft, now
from .schemas import Input


def inbox_router(settings, factory):
    router = APIRouter()
    root = "/api/organizations/{organization_id}/work-inbox"

    def actor(db, request, organization_id):
        user = authenticate(db, request_authorization(request, settings))
        member(db, user, organization_id, licensed=False)
        return user

    @router.get(root)
    def listing(
        organization_id: str, request: Request, offset: int = Query(default=0, ge=0), unread: bool = False
    ):
        with factory() as db:
            user = actor(db, request, organization_id)
            scope = (
                ChatTurn.organization_id == organization_id,
                ChatTurn.owner_id == user.id,
                ChatTurn.status.not_in(("queued", "running")),
                select(Conversation.id)
                .where(Conversation.id == ChatTurn.conversation_id, Conversation.deleted_at.is_(None))
                .correlate(ChatTurn)
                .exists(),
            )
            count = db.scalar(select(func.count(ChatTurn.id)).where(*scope, ChatTurn.seen_at.is_(None)))
            query = (
                select(ChatTurn, Conversation.title)
                .join(Conversation, Conversation.id == ChatTurn.conversation_id)
                .where(*scope)
            )
            if unread:
                query = query.where(ChatTurn.seen_at.is_(None))
            rows = db.execute(
                query.order_by(ChatTurn.created_at.desc(), ChatTurn.id).offset(offset).limit(51)
            ).all()
            items = []
            for turn, title in rows[:50]:
                accepted = (
                    select(EmailAttempt.id)
                    .where(
                        EmailAttempt.draft_id == EmailDraft.id,
                        EmailAttempt.version == EmailDraft.version,
                        EmailAttempt.status == "accepted",
                    )
                    .exists()
                )
                drafts = db.scalar(
                    select(func.count(EmailDraft.id)).where(EmailDraft.turn_id == turn.id, ~accepted)
                )
                drafts += db.scalar(
                    select(func.count(CalendarAction.id)).where(
                        CalendarAction.turn_id == turn.id, CalendarAction.status != "completed"
                    )
                )
                items.append(
                    {
                        "id": turn.id,
                        "conversation_id": turn.conversation_id,
                        "title": title,
                        "message": turn.message[:240],
                        "status": "review" if drafts else turn.status,
                        "created_at": turn.finished_at or turn.created_at,
                        "read": turn.seen_at is not None,
                    }
                )
            return {"items": items, "unread": count, "next_offset": offset + 50 if len(rows) > 50 else None}

    @router.put(root + "/{turn_id}/read")
    def mark(organization_id: str, turn_id: str, request: Request, body: Input):
        with factory.begin() as db:
            user = actor(db, request, organization_id)
            turn = owned(db, ChatTurn, organization_id, user.id, turn_id)
            if turn.status not in ("queued", "running"):
                turn.seen_at = now()
            return {"read": turn.seen_at is not None}

    return router
