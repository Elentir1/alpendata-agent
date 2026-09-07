"""Deletion revokes access and stops future work; receipts remain for reconciliation."""

from fastapi import HTTPException, Request
from sqlalchemy import delete, or_, select, update

from .models import ChatTurn, Conversation, PersonalNotification, RoutineProposal, RoutineSchedule, now
from .schedule_state import stop_schedule


def attach_deletion_route(router, factory, actor):
    @router.delete(
        "/api/organizations/{organization_id}/chat/conversations/{conversation_id}", status_code=204
    )
    def remove(organization_id: str, conversation_id: str, request: Request):
        with factory.begin() as db:
            user = actor(db, request, organization_id, licensed=False)
            item = db.scalar(
                select(Conversation)
                .where(
                    Conversation.id == conversation_id,
                    Conversation.organization_id == organization_id,
                    Conversation.owner_id == user.id,
                )
                .with_for_update()
            )
            if item is None:
                raise HTTPException(404, "resource_not_found")
            if item.deleted_at is not None:
                return
            item.deleted_at, item.archived, item.pinned = now(), True, False
            turn_ids = select(ChatTurn.id).where(ChatTurn.conversation_id == item.id)
            proposals = select(RoutineProposal.id).where(RoutineProposal.conversation_id == item.id)
            schedules = db.scalars(
                select(RoutineSchedule)
                .where(
                    RoutineSchedule.organization_id == organization_id,
                    RoutineSchedule.owner_id == user.id,
                    or_(
                        RoutineSchedule.proposal_id.in_(proposals),
                        RoutineSchedule.reviewed_turn_id.in_(turn_ids),
                    ),
                )
                .with_for_update()
            ).all()
            for schedule in schedules:
                stop_schedule(db, schedule, "archived", "conversation_deleted")
            db.execute(
                update(ChatTurn)
                .where(ChatTurn.conversation_id == item.id, ChatTurn.status == "queued")
                .values(cancel_requested=True, status="cancelled", finished_at=now())
            )
            db.execute(
                update(ChatTurn)
                .where(ChatTurn.conversation_id == item.id, ChatTurn.status == "running")
                .values(cancel_requested=True)
            )
            db.execute(
                delete(PersonalNotification).where(
                    PersonalNotification.organization_id == organization_id,
                    PersonalNotification.owner_id == user.id,
                    or_(
                        PersonalNotification.turn_id.in_(turn_ids),
                        PersonalNotification.schedule_id.in_([row.id for row in schedules]),
                    ),
                )
            )
