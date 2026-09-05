"""Private schedule management. Activation requires a reviewed, source-verified trial."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import Field
from sqlalchemy import select

from .access import owned
from .auth import authenticate, request_authorization
from .connections import lock_member
from .models import ChatTurn, RoutineOccurrence, RoutineProposal, RoutineSchedule, RoutineTrial, now
from .routine_catalog import RECIPES
from .routine_service import trial_view
from .schedule_state import cancel_occurrences, check_schedule_access, stop_schedule
from .schedule_time import Cadence, next_occurrence
from .schemas import Input

PREFIX = "/api/organizations/{organization_id}/schedules"


class ActivationInput(Cadence):
    request_id: UUID
    reviewed_trial_id: UUID
    reviewed: Literal[True]


class VersionInput(Input):
    version: int = Field(ge=1)


class ScheduleEdit(Cadence):
    version: int = Field(ge=1)


def cadence_values(body):
    return {name: getattr(body, name) for name in Cadence.model_fields}


def schedule_view(db, row):
    proposal = db.get(RoutineProposal, row.proposal_id)
    return {
        **{
            name: getattr(row, name)
            for name in (
                "id",
                "proposal_id",
                "status",
                "version",
                "next_run_at",
                "reason_code",
                "created_at",
                "updated_at",
            )
        },
        **cadence_values(row),
        "title": proposal.title,
        "focus": proposal.focus,
        "capabilities": RECIPES[proposal.template].capabilities,
    }


def schedules_router(settings, factory):
    router = APIRouter()

    def actor(db, request, organization_id, *, licensed=False):
        user = authenticate(db, request_authorization(request, settings))
        lock_member(db, user, organization_id, licensed=licensed)
        return user

    @router.get(PREFIX)
    def listing(organization_id: str, request: Request, before: int = Query(default=0, ge=0)):
        with factory.begin() as db:
            user = actor(db, request, organization_id)
            rows = db.scalars(
                select(RoutineSchedule)
                .where(
                    RoutineSchedule.organization_id == organization_id,
                    RoutineSchedule.owner_id == user.id,
                    RoutineSchedule.status != "archived",
                )
                .order_by(RoutineSchedule.created_at.desc(), RoutineSchedule.id)
                .offset(before)
                .limit(51)
            ).all()
            return {
                "schedules": [schedule_view(db, row) for row in rows[:50]],
                "next_offset": before + 50 if len(rows) > 50 else None,
            }

    @router.post(PREFIX, status_code=201)
    def activate(organization_id: str, request: Request, body: ActivationInput):
        with factory.begin() as db:
            user = actor(db, request, organization_id, licensed=True)
            trial = owned(db, RoutineTrial, organization_id, user.id, str(body.reviewed_trial_id))
            values = cadence_values(body)
            previous = db.scalar(
                select(RoutineSchedule).where(
                    RoutineSchedule.organization_id == organization_id,
                    RoutineSchedule.owner_id == user.id,
                    RoutineSchedule.activation_request_id == str(body.request_id),
                )
            )
            if previous:
                if previous.reviewed_turn_id != trial.turn_id or cadence_values(previous) != values:
                    raise HTTPException(409, "routine_request_conflict")
                return schedule_view(db, previous)
            if not trial_view(db, trial)["sources_verified"]:
                raise HTTPException(409, "routine_trial_required")
            schedule = db.scalar(
                select(RoutineSchedule).where(RoutineSchedule.proposal_id == trial.proposal_id)
            )
            replacing = (
                schedule and schedule.status == "blocked" and schedule.reviewed_turn_id != trial.turn_id
            )
            if schedule and schedule.status != "archived" and not replacing:
                raise HTTPException(409, "routine_already_exists")
            if schedule is None:
                schedule = RoutineSchedule(
                    organization_id=organization_id, owner_id=user.id, proposal_id=trial.proposal_id
                )
            else:
                schedule.version += 1
            schedule.reviewed_turn_id, schedule.activation_request_id = trial.turn_id, str(body.request_id)
            for key, value in values.items():
                setattr(schedule, key, value)
            check_schedule_access(db, settings, schedule)
            schedule.status, schedule.reason_code, schedule.failure_count = "active", None, 0
            schedule.next_run_at, schedule.updated_at = next_occurrence(body, now()), now()
            db.add(schedule)
            db.flush()
            return schedule_view(db, schedule)

    @router.patch(PREFIX + "/{schedule_id}")
    def edit(organization_id: str, schedule_id: str, request: Request, body: ScheduleEdit):
        with factory.begin() as db:
            user = actor(db, request, organization_id, licensed=True)
            row = owned(db, RoutineSchedule, organization_id, user.id, schedule_id)
            if row.version != body.version or row.status == "archived":
                raise HTTPException(409, "routine_version_changed")
            if row.status == "active":
                check_schedule_access(db, settings, row)
            if cadence_values(row) != cadence_values(body):
                cancel_occurrences(db, row)
                for key, value in cadence_values(body).items():
                    setattr(row, key, value)
                row.version += 1
                row.updated_at = now()
                row.next_run_at = next_occurrence(row, now()) if row.status == "active" else None
            return schedule_view(db, row)

    @router.post(PREFIX + "/{schedule_id}/{action}")
    def change(
        organization_id: str,
        schedule_id: str,
        action: Literal["pause", "resume", "archive"],
        request: Request,
        body: VersionInput,
    ):
        with factory.begin() as db:
            user = actor(db, request, organization_id, licensed=action == "resume")
            row = owned(db, RoutineSchedule, organization_id, user.id, schedule_id)
            if row.version != body.version or row.status == "archived":
                raise HTTPException(409, "routine_version_changed")
            status = {"pause": "paused", "resume": "active", "archive": "archived"}[action]
            if status == row.status:
                return schedule_view(db, row)
            if action == "resume":
                check_schedule_access(db, settings, row)
                row.status, row.reason_code, row.failure_count = "active", None, 0
                row.version += 1
                row.next_run_at, row.updated_at = next_occurrence(row, now()), now()
            else:
                stop_schedule(db, row, status)
            return schedule_view(db, row)

    @router.get(PREFIX + "/{schedule_id}/occurrences")
    def occurrences(
        organization_id: str,
        schedule_id: str,
        request: Request,
        before: int | None = Query(default=None, ge=0),
    ):
        with factory.begin() as db:
            user = actor(db, request, organization_id)
            owned(db, RoutineSchedule, organization_id, user.id, schedule_id)
            query = select(RoutineOccurrence).where(RoutineOccurrence.schedule_id == schedule_id)
            if before is not None:
                query = query.where(RoutineOccurrence.scheduled_for < before)
            rows = db.scalars(query.order_by(RoutineOccurrence.scheduled_for.desc()).limit(51)).all()
            result = []
            for row in rows[:50]:
                turn = db.get(ChatTurn, row.turn_id) if row.turn_id else None
                result.append(
                    {
                        "id": row.id,
                        "scheduled_for": row.scheduled_for,
                        "version": row.schedule_version,
                        "status": turn.status if turn else row.outcome,
                        "error_code": turn.error_code if turn else None,
                        "conversation_id": turn.conversation_id if turn else None,
                    }
                )
            return {"occurrences": result, "next_before": rows[49].scheduled_for if len(rows) > 50 else None}

    return router
