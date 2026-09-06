"""Create a durable personal notification in the source transaction, under the owner lock."""

from sqlalchemy import select

from .models import PersonalNotification, RoutineProposal


def record_notification(db, schedule, source_key, status, *, turn=None, error=None):
    existing = db.scalar(
        select(PersonalNotification.id).where(
            PersonalNotification.organization_id == schedule.organization_id,
            PersonalNotification.owner_id == schedule.owner_id,
            PersonalNotification.source_key == source_key,
        )
    )
    if existing:
        return
    proposal = db.get(RoutineProposal, schedule.proposal_id)
    db.add(
        PersonalNotification(
            organization_id=schedule.organization_id,
            owner_id=schedule.owner_id,
            schedule_id=schedule.id,
            source_key=source_key,
            title=proposal.title,
            status=status,
            turn_id=turn.id if turn else None,
            error_code=error,
        )
    )
