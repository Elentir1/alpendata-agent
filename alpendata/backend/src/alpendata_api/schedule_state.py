"""Schedule state changes share the owner's membership lock with agent authorization."""

from fastapi import HTTPException
from sqlalchemy import select, update

from .models import ChatTurn, Conversation, MicrosoftConnection, RoutineOccurrence, RoutineSchedule, now
from .notification_events import record_notification
from .organization_policy import require_allowed

CATCH_UP_SECONDS = 7200


def occurrence_for_turn(db, turn_id):
    return db.scalar(select(RoutineOccurrence).where(RoutineOccurrence.turn_id == turn_id))


def cancel_occurrences(db, schedule):
    ids = select(RoutineOccurrence.turn_id).where(RoutineOccurrence.schedule_id == schedule.id)
    db.execute(
        update(ChatTurn)
        .where(ChatTurn.id.in_(ids), ChatTurn.status == "queued")
        .values(status="cancelled", cancel_requested=True, finished_at=now())
    )
    db.execute(
        update(ChatTurn)
        .where(ChatTurn.id.in_(ids), ChatTurn.status == "running")
        .values(cancel_requested=True)
    )


def stop_schedule(db, schedule, status, reason=None):
    schedule.status, schedule.reason_code, schedule.next_run_at = status, reason, None
    schedule.version += 1
    schedule.updated_at = now()
    cancel_occurrences(db, schedule)
    if status == "blocked":
        record_notification(
            db, schedule, f"blocked:{schedule.id}:{schedule.version}", "blocked", error=reason
        )


def block_owner_schedules(db, organization_id, owner_id, reason, *, available=None, autonomous_only=False):
    rows = db.scalars(
        select(RoutineSchedule)
        .where(
            RoutineSchedule.organization_id == organization_id,
            RoutineSchedule.owner_id == owner_id,
            RoutineSchedule.status == "active",
        )
        .with_for_update()
    ).all()
    for row in rows:
        turn = db.get(ChatTurn, row.reviewed_turn_id)
        conversation = db.get(Conversation, turn.conversation_id)
        if autonomous_only and not conversation.email_send_enabled:
            continue
        if available is not None:
            required = set(conversation.capabilities) | (
                {"mail_send"} if conversation.email_send_enabled else set()
            )
            if required <= set(available):
                continue
        stop_schedule(db, row, "blocked", reason)


def check_schedule_access(db, settings, schedule):
    turn = db.get(ChatTurn, schedule.reviewed_turn_id)
    conversation = db.get(Conversation, turn.conversation_id)
    require_allowed(db, schedule.organization_id, conversation.capabilities)
    if conversation.email_send_enabled:
        from .action_policy import require_email_autonomy

        require_email_autonomy(db, schedule.organization_id, schedule.owner_id)
    if not settings.chat_enabled:
        raise HTTPException(503, "chat_not_configured")
    if (conversation.provider, conversation.model) != (settings.model.provider, settings.model.model):
        raise HTTPException(409, "chat_model_changed")
    if not conversation.capabilities and not conversation.email_send_enabled:
        return conversation
    connection = db.scalar(
        select(MicrosoftConnection).where(
            MicrosoftConnection.organization_id == schedule.organization_id,
            MicrosoftConnection.owner_id == schedule.owner_id,
        )
    )
    if (
        connection is None
        or connection.status != "connected"
        or not set(conversation.capabilities) <= set(connection.capabilities)
        or (conversation.email_send_enabled and "mail_send" not in connection.capabilities)
    ):
        raise HTTPException(409, "microsoft_reconnect_required")
    return conversation


def scheduled_turn_error(db, turn):
    if db.get(Conversation, turn.conversation_id).purpose != "scheduled":
        return None
    occurrence = occurrence_for_turn(db, turn.id)
    if occurrence is None:
        # A user may continue the result conversation manually after delivery.
        return None
    schedule = db.get(RoutineSchedule, occurrence.schedule_id)
    if schedule.status != "active" or schedule.version != occurrence.schedule_version:
        return "agent_cancelled"
    if now() > occurrence.scheduled_for + CATCH_UP_SECONDS:
        return "routine_occurrence_expired"
    return None


def finish_occurrence(db, turn, error):
    occurrence = occurrence_for_turn(db, turn.id)
    if occurrence is None:
        return
    schedule = db.get(RoutineSchedule, occurrence.schedule_id)
    if turn.status in {"completed", "failed", "interrupted"}:
        record_notification(
            db, schedule, f"occurrence:{occurrence.id}", turn.status, turn=turn, error=turn.error_code
        )
    if schedule.status != "active" or schedule.version != occurrence.schedule_version:
        return
    schedule.failure_count = schedule.failure_count + 1 if error else 0
    if schedule.failure_count >= 3:
        stop_schedule(db, schedule, "blocked", "routine_repeated_failures")
