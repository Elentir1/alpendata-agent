"""Read shared company copies with the current employee's grants, never another connection."""

import base64
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import Field, model_validator

from .company_resources import resource_list, resource_view, visible_resource
from .models import Conversation, Membership, ToolRead, now
from .schemas import Input


class ResourceRequest(Input):
    action: Literal["search", "read", "download"]
    query: str = Field(default="", max_length=160)
    before: int = Field(default=0, ge=0)
    resource_id: UUID | None = None
    version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def arguments_match(self):
        if self.action == "search":
            if self.resource_id is not None or self.version is not None:
                raise ValueError("Search uses a query and page")
        elif self.resource_id is None or self.version is None or self.query or self.before:
            raise ValueError("Reading requires a resource and version")
        return self


def read_company_resource(db, turn, payload):
    request = ResourceRequest.model_validate(payload)
    if db.get(Conversation, turn.conversation_id).tool_revision < 5:
        raise HTTPException(403, "company_resource_new_conversation_required")
    membership = db.get(Membership, (turn.organization_id, turn.owner_id))
    if request.action == "search":
        return resource_list(db, turn.organization_id, membership, query=request.query, before=request.before)
    row = visible_resource(db, turn.organization_id, membership, str(request.resource_id), request.version)
    if (request.action == "read") != (row.kind == "note"):
        raise HTTPException(400, "company_resource_action_invalid")
    source = resource_view(db, row, include_text=request.action == "read")
    db.add(
        ToolRead(
            organization_id=turn.organization_id,
            owner_id=turn.owner_id,
            turn_id=turn.id,
            capability="company_resources",
            status="completed",
            finished_at=now(),
            sources=[
                {
                    "kind": "company_resource",
                    "id": row.id,
                    "version": row.version,
                    "label": f"{row.title} · v{row.version}",
                    "url": None,
                }
            ],
        )
    )
    if request.action == "read":
        return {"resource": source, "shared_company_copy": True}
    return {
        "files": [{**source, "name": row.filename, "shared_company_copy": True}],
        "content_base64": base64.b64encode(row.content).decode("ascii"),
    }
