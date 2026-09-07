"""Explicit personal preferences and portable procedures; project facts stay in projects."""

from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field
from sqlalchemy import func, select

from .access import owned
from .auth import authenticate, request_authorization
from .connections import lock_member
from .models import PersonalKnowledge
from .schemas import Input


class KnowledgeInput(Input):
    kind: Literal["preference", "method"]
    title: str = Field(min_length=1, max_length=160, pattern=r"\S")
    content: str = Field(min_length=1, max_length=20000, pattern=r"\S")
    version: int = Field(default=0, ge=0)


def view(row):
    return {key: getattr(row, key) for key in ("id", "kind", "title", "content", "version")}


def save(db, organization_id, owner_id, identifier, body):
    row = db.scalar(select(PersonalKnowledge).where(PersonalKnowledge.id == identifier).with_for_update())
    if row:
        if (row.organization_id, row.owner_id) != (organization_id, owner_id):
            raise HTTPException(404, "resource_not_found")
        if body.version == 0 and (row.kind, row.title, row.content) == (body.kind, body.title, body.content):
            return row
        if row.version != body.version:
            raise HTTPException(409, "knowledge_version_changed")
        row.kind, row.title, row.content, row.version = body.kind, body.title, body.content, row.version + 1
    else:
        if body.version:
            raise HTTPException(409, "knowledge_version_changed")
        count = db.scalar(
            select(func.count(PersonalKnowledge.id)).where(
                PersonalKnowledge.organization_id == organization_id, PersonalKnowledge.owner_id == owner_id
            )
        )
        if count >= 200:
            raise HTTPException(409, "knowledge_capacity_reached")
        row = PersonalKnowledge(
            id=identifier,
            organization_id=organization_id,
            owner_id=owner_id,
            kind=body.kind,
            title=body.title,
            content=body.content,
        )
        db.add(row)
    db.flush()
    return row


def knowledge_router(settings, factory):
    router = APIRouter()
    root = "/api/organizations/{organization_id}/knowledge"

    def actor(db, request, organization_id, write=False):
        user = authenticate(db, request_authorization(request, settings))
        lock_member(db, user, organization_id, licensed=write)
        return user

    @router.get(root)
    def listing(organization_id: str, request: Request):
        with factory.begin() as db:
            user = actor(db, request, organization_id)
            rows = db.scalars(
                select(PersonalKnowledge)
                .where(
                    PersonalKnowledge.organization_id == organization_id,
                    PersonalKnowledge.owner_id == user.id,
                )
                .order_by(PersonalKnowledge.title)
            ).all()
            return {"entries": [view(row) for row in rows]}

    @router.put(root + "/{entry_id}")
    def update(organization_id: str, entry_id: UUID, request: Request, body: KnowledgeInput):
        with factory.begin() as db:
            user = actor(db, request, organization_id, write=True)
            return view(save(db, organization_id, user.id, str(entry_id), body))

    @router.delete(root + "/{entry_id}", status_code=204)
    def delete(organization_id: str, entry_id: UUID, request: Request):
        with factory.begin() as db:
            user = actor(db, request, organization_id)
            db.delete(owned(db, PersonalKnowledge, organization_id, user.id, str(entry_id)))

    return router


class ToolInput(Input):
    operation: Literal["list", "read", "save"]
    entry_id: UUID | None = None
    category: Literal["preference", "method"] = "method"
    title: str = Field(default="", max_length=160)
    content: str = Field(default="", max_length=20000)
    version: int = Field(default=0, ge=0)


def knowledge_tool(db, turn, payload):
    body = ToolInput.model_validate(payload)
    query = select(PersonalKnowledge).where(
        PersonalKnowledge.organization_id == turn.organization_id,
        PersonalKnowledge.owner_id == turn.owner_id,
        PersonalKnowledge.kind == body.category,
    )
    if body.operation == "list":
        return {
            "entries": [
                {"id": row.id, "title": row.title, "kind": row.kind, "version": row.version}
                for row in db.scalars(query.order_by(PersonalKnowledge.title)).all()
            ]
        }
    if body.operation == "read":
        return view(owned(db, PersonalKnowledge, turn.organization_id, turn.owner_id, str(body.entry_id)))
    data = KnowledgeInput(kind=body.category, title=body.title, content=body.content, version=body.version)
    return view(save(db, turn.organization_id, turn.owner_id, str(body.entry_id or uuid4()), data))
