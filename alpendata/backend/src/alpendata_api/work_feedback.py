"""Explicit feedback and company aggregates; no conversation content is disclosed."""

from statistics import median
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import func, or_, select

from .access import member, owned
from .auth import authenticate, request_authorization
from .connections import lock_member
from .models import ChatTurn, Conversation, Onboarding, WorkFeedback, now
from .schemas import Input


class FeedbackInput(Input):
    outcome: Literal["useful", "needs_changes", "not_useful"]


def feedback_available(db, turn):
    conversation = db.get(Conversation, turn.conversation_id)
    return bool(
        turn.status == "completed"
        and turn.response
        and (not conversation.parent_id or turn.sequence > (conversation.branch_sequence or 0))
    )


def feedback_router(settings, factory):
    router = APIRouter()
    root = "/api/organizations/{organization_id}"

    @router.put(root + "/chat/conversations/{conversation_id}/turns/{turn_id}/feedback")
    def save(organization_id: str, conversation_id: str, turn_id: str, request: Request, body: FeedbackInput):
        with factory.begin() as db:
            user = authenticate(db, request_authorization(request, settings))
            lock_member(db, user, organization_id, licensed=False)
            turn = owned(db, ChatTurn, organization_id, user.id, turn_id)
            if turn.conversation_id != conversation_id:
                raise HTTPException(404, "resource_not_found")
            if not feedback_available(db, turn):
                raise HTTPException(409, "feedback_result_required")
            feedback = db.get(WorkFeedback, turn.id)
            if not feedback:
                feedback = WorkFeedback(turn_id=turn.id, organization_id=organization_id, owner_id=user.id)
                db.add(feedback)
            feedback.outcome, feedback.updated_at = body.outcome, now()
            if body.outcome == "useful":
                profile = db.scalar(
                    select(Onboarding).where(
                        Onboarding.organization_id == organization_id, Onboarding.owner_id == user.id
                    )
                )
                if profile and profile.first_useful_at is None:
                    profile.first_useful_at = now()
            return {"outcome": feedback.outcome}

    @router.get(root + "/work-metrics")
    def metrics(organization_id: str, request: Request):
        with factory() as db:
            user = authenticate(db, request_authorization(request, settings))
            member(db, user, organization_id, admin=True, licensed=False)
            statuses = dict(
                db.execute(
                    select(ChatTurn.status, func.count(ChatTurn.id))
                    .join(Conversation, Conversation.id == ChatTurn.conversation_id)
                    .where(
                        ChatTurn.organization_id == organization_id,
                        or_(
                            Conversation.parent_id.is_(None), ChatTurn.sequence > Conversation.branch_sequence
                        ),
                    )
                    .group_by(ChatTurn.status)
                ).all()
            )
            feedback = dict(
                db.execute(
                    select(WorkFeedback.outcome, func.count(WorkFeedback.turn_id))
                    .where(WorkFeedback.organization_id == organization_id)
                    .group_by(WorkFeedback.outcome)
                ).all()
            )
            timing = db.execute(
                select(Onboarding.first_useful_at, Onboarding.started_at).where(
                    Onboarding.organization_id == organization_id,
                    Onboarding.started_at.is_not(None),
                    Onboarding.first_useful_at.is_not(None),
                )
            ).all()
            durations = [max(0, useful - started) for useful, started in timing]
            started = db.scalar(
                select(func.count(Onboarding.id)).where(
                    Onboarding.organization_id == organization_id, Onboarding.started_at.is_not(None)
                )
            )
            incomplete = db.scalar(
                select(func.count(Onboarding.id)).where(
                    Onboarding.organization_id == organization_id,
                    Onboarding.started_at <= now() - 7 * 86400,
                    Onboarding.first_useful_at.is_(None),
                )
            )
            return {
                "executions": statuses,
                "feedback": feedback,
                "feedback_count": sum(feedback.values()),
                "first_useful_median_seconds": median(durations) if durations else None,
                "first_useful_sample_size": len(durations),
                "onboarding_started": started,
                "without_reported_useful_result_after_days": {"days": 7, "count": incomplete},
            }

    return router
