"""One database schedule authority; each occurrence runs through the existing Hermes queue."""

import time
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select

from .chat import queue_turn
from .connections import lock_member
from .database import database_factory
from .models import Conversation, RoutineOccurrence, RoutineProposal, RoutineSchedule, User, now
from .schedule_state import CATCH_UP_SECONDS, check_schedule_access, stop_schedule
from .schedule_time import next_occurrence
from .settings import Settings


class ScheduleWorker:
    def __init__(self, settings, factory):
        self.settings, self.factory = settings, factory

    def tick(self, at=None):
        at = now() if at is None else at
        with self.factory() as db:
            candidates = db.scalars(
                select(RoutineSchedule)
                .where(
                    RoutineSchedule.status == "active",
                    RoutineSchedule.next_run_at <= at,
                )
                .order_by(RoutineSchedule.next_run_at, RoutineSchedule.id)
                .limit(100)
            ).all()
        processed = 0
        for candidate in candidates:
            with self.factory.begin() as db:
                user = db.get(User, candidate.owner_id)
                denied = None
                try:
                    lock_member(db, user, candidate.organization_id)
                    if not user.active:
                        denied = "agent_access_revoked"
                except HTTPException:
                    denied = "agent_access_revoked"
                row = db.scalar(
                    select(RoutineSchedule).where(RoutineSchedule.id == candidate.id).with_for_update()
                )
                if row.status != "active" or row.next_run_at is None or row.next_run_at > at:
                    continue
                if denied:
                    stop_schedule(db, row, "blocked", denied)
                    continue
                try:
                    template = check_schedule_access(db, self.settings, row)
                except HTTPException as error:
                    stop_schedule(db, row, "blocked", error.detail)
                    continue
                due = row.next_run_at
                occurrence = RoutineOccurrence(
                    organization_id=row.organization_id,
                    owner_id=row.owner_id,
                    schedule_id=row.id,
                    schedule_version=row.version,
                    scheduled_for=due,
                    outcome="missed",
                )
                if at - due <= CATCH_UP_SECONDS:
                    proposal = db.get(RoutineProposal, row.proposal_id)
                    conversation = Conversation(
                        organization_id=row.organization_id,
                        owner_id=row.owner_id,
                        title=proposal.title,
                        language=template.language,
                        purpose="scheduled",
                        documents_enabled=template.documents_enabled,
                        tool_revision=template.tool_revision,
                        email_send_enabled=template.email_send_enabled,
                        email_delivery=template.email_delivery,
                        provider=template.provider,
                        model=template.model,
                        capabilities=list(template.capabilities),
                        system_prompt=template.system_prompt
                        + "\nSchedule context: the owner has now explicitly "
                        "activated this reviewed task. Perform this occurrence once. Return the result here. "
                        + (
                            "Do not change schedules or create other tasks. Send email only when this "
                            "reviewed task requests it, through the authorized email tool."
                            if template.email_send_enabled
                            else "Do not change schedules, create other tasks or perform external writes."
                        ),
                    )
                    db.add(conversation)
                    db.flush()
                    message = (
                        "Exécuter la tâche planifiée une fois."
                        if template.language == "fr"
                        else "Execute the scheduled task once."
                    )
                    turn = queue_turn(
                        db, self.settings, user, conversation, uuid4(), message, allow_waiting=True
                    )
                    occurrence.turn_id, occurrence.outcome = turn.id, "queued"
                db.add(occurrence)
                row.next_run_at = next_occurrence(row, at)
                processed += 1
        return processed


def main():
    settings = Settings.from_environment()
    engine, factory = database_factory(settings.database_url)
    try:
        worker = ScheduleWorker(settings, factory)
        while True:
            worker.tick()
            time.sleep(30)
    except KeyboardInterrupt:
        return
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
