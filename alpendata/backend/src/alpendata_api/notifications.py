"""Notifications are committed with their source event, under the owner's lock."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import and_, func, or_, select

from .access import owned
from .auth import authenticate, request_authorization
from .connections import lock_member
from .models import ChatTurn, Conversation, PersonalNotification, now
from .schemas import Input


def view(db, row):
    turn = db.get(ChatTurn, row.turn_id) if row.turn_id else None
    return {
        **{
            key: getattr(row, key)
            for key in ("id", "title", "status", "error_code", "schedule_id", "created_at", "read_at")
        },
        "conversation_id": turn.conversation_id if turn else None,
    }


def notifications_router(settings, factory):
    router = APIRouter()
    base = "/api/organizations/{organization_id}/notifications"

    def actor(db, request, organization_id):
        user = authenticate(db, request_authorization(request, settings))
        lock_member(db, user, organization_id, licensed=False)
        return user

    @router.get(base)
    def listing(
        organization_id: str,
        request: Request,
        count_only: bool = False,
        before: int | None = Query(default=None, ge=0),
        before_id: UUID | None = None,
    ):
        if (before is None) != (before_id is None):
            raise HTTPException(422, "notification_cursor_invalid")
        with factory.begin() as db:
            user = actor(db, request, organization_id)
            scope = (
                PersonalNotification.organization_id == organization_id,
                PersonalNotification.owner_id == user.id,
                or_(
                    PersonalNotification.turn_id.is_(None),
                    select(ChatTurn.id)
                    .join(Conversation, Conversation.id == ChatTurn.conversation_id)
                    .where(ChatTurn.id == PersonalNotification.turn_id, Conversation.deleted_at.is_(None))
                    .correlate(PersonalNotification)
                    .exists(),
                ),
            )
            unread = db.scalar(
                select(func.count())
                .select_from(PersonalNotification)
                .where(*scope, PersonalNotification.read_at.is_(None))
            )
            if count_only:
                return {"unread": unread}
            query = select(PersonalNotification).where(*scope)
            if before is not None:
                query = query.where(
                    or_(
                        PersonalNotification.created_at < before,
                        and_(
                            PersonalNotification.created_at == before,
                            PersonalNotification.id < str(before_id),
                        ),
                    )
                )
            rows = db.scalars(
                query.order_by(PersonalNotification.created_at.desc(), PersonalNotification.id.desc()).limit(
                    26
                )
            ).all()
            return {
                "unread": unread,
                "notifications": [view(db, row) for row in rows[:25]],
                "next_before": {"at": rows[24].created_at, "id": rows[24].id} if len(rows) > 25 else None,
            }

    @router.put(base + "/{notification_id}/read")
    def mark_read(organization_id: str, notification_id: str, request: Request, body: Input):
        with factory.begin() as db:
            user = actor(db, request, organization_id)
            row = owned(db, PersonalNotification, organization_id, user.id, notification_id)
            if row.read_at is None:
                row.read_at = now()
            return view(db, row)

    return router
