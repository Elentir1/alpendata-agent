"""The authenticated owner manages the same private memory used by Hermes."""

from dataclasses import replace
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field, ValidationError
from sqlalchemy import select

from .auth import authenticate, request_authorization
from .connections import lock_member
from .models import ChatTurn
from .runtime import ContainerRuntime, RuntimeFailure
from .schemas import Input

Entry = Annotated[str, Field(max_length=65536)]
Version = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class MemoryEdit(Input):
    version: Version
    entries: list[Entry] = Field(max_length=2500)


class MemoryView(MemoryEdit):
    limit: int = Field(ge=1, le=65536)


class Memories(Input):
    memory: MemoryView
    user: MemoryView


def memory_router(settings, factory):
    router = APIRouter()
    base = "/api/organizations/{organization_id}/memory"

    def actor(db, request, organization_id):
        user = authenticate(db, request_authorization(request, settings))
        # Owners retain control over their data after losing a paid seat.
        lock_member(db, user, organization_id, licensed=False)
        return user

    def run(db, user, organization_id, payload):
        if settings.runtime is None:
            raise HTTPException(503, "memory_not_configured")
        active = db.scalar(
            select(ChatTurn.id)
            .where(
                ChatTurn.organization_id == organization_id,
                ChatTurn.owner_id == user.id,
                ChatTurn.status.in_(("queued", "running")),
            )
            .limit(1)
        )
        if active:
            raise HTTPException(409, "agent_already_running")

        def no_broker(_operation, _body):
            raise RuntimeFailure("agent_protocol_invalid")

        try:
            runtime = ContainerRuntime(replace(settings.runtime, timeout_seconds=30))
            result = runtime.run(organization_id, user.id, {"operation": "memory", **payload}, no_broker)
        except RuntimeFailure as error:
            code = str(error)
            if code in {"agent_already_running", "agent_recovery_required"}:
                raise HTTPException(409, code) from None
            raise HTTPException(503, "memory_unavailable") from None
        error = result.get("memory_error")
        if error:
            statuses = {
                "memory_changed": 409,
                "memory_request_invalid": 422,
                "memory_limit_exceeded": 422,
                "memory_content_rejected": 422,
                "memory_state_invalid": 409,
                "memory_too_large": 409,
                "memory_unreadable": 409,
                "memory_update_failed": 503,
                "memory_unavailable": 503,
            }
            raise HTTPException(
                statuses.get(error, 503), error if error in statuses else "memory_unavailable"
            )
        try:
            memory = Memories.model_validate(result.get("memory"))
        except ValidationError:
            raise HTTPException(503, "memory_unavailable") from None
        return {"available": True, **memory.model_dump()}

    @router.get(base)
    def read(organization_id: str, request: Request):
        with factory.begin() as db:
            user = actor(db, request, organization_id)
            if settings.runtime is None:
                return {"available": False}
            return run(db, user, organization_id, {"action": "read"})

    @router.put(base + "/{target}")
    def update(organization_id: str, target: Literal["memory", "user"], request: Request, body: MemoryEdit):
        with factory.begin() as db:
            user = actor(db, request, organization_id)
            return run(db, user, organization_id, {"action": "update", "target": target, **body.model_dump()})

    return router
