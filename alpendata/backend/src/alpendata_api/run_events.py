"""Durable, resumable activity feed. Never persist tool arguments or reasoning."""

import asyncio
import json
import time

from fastapi import HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from .access import member, owned
from .auth import authenticate, request_authorization
from .models import AgentEvent, Conversation


def record_event(db, turn, kind, label=""):
    event = AgentEvent(
        organization_id=turn.organization_id,
        owner_id=turn.owner_id,
        conversation_id=turn.conversation_id,
        turn_id=turn.id,
        kind=kind,
        label=label[:120],
    )
    db.add(event)
    return event


def event_view(row):
    return {
        "id": row.id,
        "turn_id": row.turn_id,
        "kind": row.kind,
        "label": row.label,
        "created_at": row.created_at,
    }


def attach_event_routes(router, settings, factory):
    prefix = "/api/organizations/{organization_id}/chat/conversations/{conversation_id}/events"

    def read(request, organization_id, conversation_id, after):
        with factory() as db:
            user = authenticate(db, request_authorization(request, settings))
            member(db, user, organization_id, licensed=False)
            owned(db, Conversation, organization_id, user.id, conversation_id)
            rows = db.scalars(
                select(AgentEvent)
                .where(
                    AgentEvent.organization_id == organization_id,
                    AgentEvent.owner_id == user.id,
                    AgentEvent.conversation_id == conversation_id,
                    AgentEvent.id > after,
                )
                .order_by(AgentEvent.id)
                .limit(200)
            ).all()
            return [event_view(row) for row in rows]

    @router.get(prefix)
    async def events(
        organization_id: str,
        conversation_id: str,
        request: Request,
        after: int = Query(default=0, ge=0),
        stream: bool = False,
    ):
        try:
            cursor = max(after, int(request.headers.get("last-event-id", "0")))
        except ValueError:
            raise HTTPException(422, "event_cursor_invalid") from None
        initial = await asyncio.to_thread(read, request, organization_id, conversation_id, cursor)
        if not stream:
            return {"events": initial, "next_after": initial[-1]["id"] if initial else cursor}

        async def generate():
            last, batch, deadline = cursor, initial, time.monotonic() + 25
            while time.monotonic() < deadline and not await request.is_disconnected():
                for event in batch:
                    last = event["id"]
                    yield f"id: {last}\nevent: activity\ndata: {json.dumps(event)}\n\n"
                yield ": heartbeat\n\n"
                await asyncio.sleep(1)
                try:
                    # Re-check the session and membership throughout an open stream.
                    batch = await asyncio.to_thread(read, request, organization_id, conversation_id, last)
                except HTTPException:
                    yield "event: revoked\ndata: {}\n\n"
                    return

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-store",
                "X-Accel-Buffering": "no",
            },
        )
