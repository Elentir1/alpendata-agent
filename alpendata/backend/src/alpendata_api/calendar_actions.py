"""Calendar changes use a reviewable snapshot and one durable dispatch per version."""

import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field, field_validator, model_validator
from sqlalchemy import func, select

from .access import owned
from .auth import authenticate, request_authorization
from .calendar_provider import dav_prepare, dav_write, graph_prepare, graph_write
from .connections import MicrosoftReader, lock_member
from .email_drafts import MessageInput
from .infomaniak import InfomaniakReader
from .models import CalendarAction, ChatTurn, Conversation, new_id, now
from .organization_policy import require_allowed
from .runtime import RuntimeFailure
from .schemas import Input
from .work_settings import source_allowed


class EventInput(Input):
    subject: str = Field(min_length=1, max_length=500, pattern=r"\S")
    description: str = Field(default="", max_length=20000)
    start: datetime
    end: datetime
    location: str = Field(default="", max_length=500)
    attendees: list[str] = Field(default_factory=list, max_length=20)
    event_id: str = Field(default="", max_length=2048)
    calendar_id: str = Field(default="", max_length=2048)

    @field_validator("attendees")
    @classmethod
    def addresses(cls, values):
        return MessageInput.addresses(values)

    @model_validator(mode="after")
    def times(self):
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("An explicit timezone offset is required")
        self.start, self.end = self.start.astimezone(timezone.utc), self.end.astimezone(timezone.utc)
        if self.end <= self.start or (self.end - self.start).days > 31:
            raise ValueError("Invalid appointment duration")
        return self


class EditInput(Input):
    version: int = Field(ge=1)
    message: EventInput


class ExecuteInput(Input):
    version: int = Field(ge=1)


def view(row):
    status = row.status
    if status == "dispatching" and row.attempts and row.attempts[-1]["created_at"] + 180 < now():
        status = "unknown"
    return {
        "id": row.id,
        "version": row.version,
        "provider": row.provider,
        "message": row.message,
        "status": status,
        "attempts": row.attempts,
        "previous": {
            key: value
            for key, value in row.baseline.items()
            if key in ("subject", "start", "end", "calendar_name")
        },
    }


def turn_calendar(db, turn):
    return [
        view(row)
        for row in db.scalars(
            select(CalendarAction)
            .where(CalendarAction.turn_id == turn.id)
            .order_by(CalendarAction.created_at)
        ).all()
    ]


class CalendarService:
    def __init__(self, settings, factory, microsoft=None, infomaniak=None):
        self.settings, self.factory = settings, factory
        self.microsoft = microsoft or MicrosoftReader(settings, factory)
        self.infomaniak = infomaniak or InfomaniakReader(settings, factory)

    def prepare(self, organization_id, authorize, turn_id, payload):
        data = EventInput.model_validate(payload).model_dump(mode="json")
        digest = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
        with self.factory.begin() as db:
            user = authorize(db)
            turn = owned(db, ChatTurn, organization_id, user.id, turn_id)
            conversation = db.get(Conversation, turn.conversation_id)
            if conversation.tool_revision < 7 or not source_allowed(conversation, "calendar"):
                raise HTTPException(403, "source_not_authorized")
            previous = db.scalar(
                select(CalendarAction).where(
                    CalendarAction.turn_id == turn.id, CalendarAction.initial_hash == digest
                )
            )
            if previous:
                return view(previous)
            provider = conversation.integration_provider
        if provider == "infomaniak":
            baseline = self.infomaniak.execute(
                organization_id,
                authorize,
                "calendar",
                lambda _transport, credentials: dav_prepare(self.infomaniak.dav, credentials, data),
            )
        else:
            baseline = self.microsoft.execute(
                organization_id,
                authorize,
                "calendar",
                lambda graph, token: graph_prepare(graph, token, data["event_id"]),
            )
        with self.factory.begin() as db:
            user = authorize(db)
            previous = db.scalar(
                select(CalendarAction).where(
                    CalendarAction.turn_id == turn_id, CalendarAction.initial_hash == digest
                )
            )
            if previous:
                return view(previous)
            count = db.scalar(select(func.count(CalendarAction.id)).where(CalendarAction.turn_id == turn_id))
            if count >= 10:
                raise HTTPException(409, "calendar_proposal_limit")
            row = CalendarAction(
                organization_id=organization_id,
                owner_id=user.id,
                turn_id=turn_id,
                initial_hash=digest,
                provider=provider,
                message=data,
                baseline=baseline,
            )
            db.add(row)
            db.flush()
            return view(row)

    def dispatch(self, organization_id, authorize, action_id, version, *, automatic_turn=None):
        def check(db):
            user = authorize(db)
            row = owned(db, CalendarAction, organization_id, user.id, action_id)
            conversation = db.get(Conversation, db.get(ChatTurn, row.turn_id).conversation_id)
            if not source_allowed(conversation, "calendar"):
                raise HTTPException(403, "source_not_authorized")
            require_allowed(db, organization_id, ["calendar_write"])
            if automatic_turn:
                require_allowed(db, organization_id, ["calendar_autonomous"])
                if (
                    row.turn_id != automatic_turn
                    or (conversation.work_settings or {}).get("autonomy") != "authorized"
                ):
                    raise HTTPException(403, "calendar_confirmation_required")
            return user

        with self.factory.begin() as db:
            user = check(db)
            row = owned(db, CalendarAction, organization_id, user.id, action_id)
            if row.version != version:
                raise HTTPException(409, "calendar_proposal_changed")
            if row.status != "draft":
                return view(row)
            identifier = new_id()
            row.status = "dispatching"
            row.attempts = [
                *row.attempts,
                {
                    "id": identifier,
                    "version": version,
                    "status": "dispatching",
                    "created_at": now(),
                    "initiator": "assistant" if automatic_turn else "user",
                },
            ]
            provider, data, baseline = row.provider, row.message, row.baseline
        # This commit precedes the external call. A crash cannot recreate permission to send.
        try:
            if provider == "infomaniak":
                result = self.infomaniak.execute(
                    organization_id,
                    check,
                    "calendar_write",
                    lambda _transport, credentials: dav_write(
                        self.infomaniak.dav, credentials, identifier, data, baseline
                    ),
                )
            else:
                result = self.microsoft.execute(
                    organization_id,
                    check,
                    "calendar_write",
                    lambda graph, token: graph_write(graph, token, identifier, data, baseline),
                )
            status, error = "completed", None
        except (HTTPException, RuntimeFailure) as failure:
            error = str(failure.detail) if isinstance(failure, HTTPException) else str(failure)
            status = (
                "unknown" if error in ("calendar_result_unknown", "infomaniak_write_unknown") else "failed"
            )
            result = {}
        except Exception:
            status, error, result = "unknown", "calendar_result_unknown", {}
        with self.factory.begin() as db:
            row = db.scalar(select(CalendarAction).where(CalendarAction.id == action_id).with_for_update())
            row.status = status
            row.attempts = [
                *row.attempts[:-1],
                {
                    **row.attempts[-1],
                    "status": status,
                    "finished_at": now(),
                    "error": error,
                    "result": result,
                },
            ]
        with self.factory.begin() as db:
            user = authorize(db)
            return view(owned(db, CalendarAction, organization_id, user.id, action_id))


def calendar_router(settings, factory, microsoft_provider=None, graph=None):
    router = APIRouter()
    service = CalendarService(
        settings, factory, MicrosoftReader(settings, factory, microsoft_provider, graph)
    )
    root = "/api/organizations/{organization_id}/calendar-actions/{action_id}"

    def actor(db, request, org):
        user = authenticate(db, request_authorization(request, settings))
        lock_member(db, user, org)
        return user

    @router.put(root)
    def edit(organization_id: str, action_id: UUID, request: Request, body: EditInput):
        with factory.begin() as db:
            user = actor(db, request, organization_id)
            row = owned(db, CalendarAction, organization_id, user.id, str(action_id))
            if row.version != body.version or row.status not in ("draft", "failed"):
                raise HTTPException(409, "calendar_proposal_changed")
            message = body.message.model_dump(mode="json")
            if (message["event_id"], message["calendar_id"]) != (
                row.message["event_id"],
                row.message["calendar_id"],
            ):
                raise HTTPException(422, "calendar_target_immutable")
            row.message, row.version, row.status = message, row.version + 1, "draft"
            return view(row)

    @router.post(root + "/execute")
    def execute(organization_id: str, action_id: UUID, request: Request, body: ExecuteInput):
        return service.dispatch(
            organization_id, lambda db: actor(db, request, organization_id), str(action_id), body.version
        )

    return router
