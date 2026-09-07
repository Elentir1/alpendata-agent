"""Explicit publication creates an independent snapshot, never a credential grant."""

from typing import Literal
from uuid import UUID, uuid4

from fastapi import HTTPException, Request
from pydantic import Field
from sqlalchemy import select

from .models import Membership, ProjectEntry, ProjectMember, User
from .project_access import project_access
from .schemas import Input


class MemberInput(Input):
    user_id: UUID
    role: Literal["reader", "contributor"] = "reader"


class EntryInput(Input):
    title: str = Field(min_length=1, max_length=160, pattern=r"\S")
    content: str = Field(min_length=1, max_length=100000, pattern=r"\S")
    kind: Literal["note", "publication", "method"] = "note"
    request_id: UUID | None = None
    version: int = Field(default=1, ge=1)


def entry_view(item):
    return {key: getattr(item, key) for key in ("id", "title", "content", "kind", "version", "owner_id")}


def attach_sharing_routes(router, factory, actor):
    prefix = "/api/organizations/{organization_id}/chat/projects/{project_id}"

    @router.get(prefix + "/members")
    def members(organization_id: str, project_id: str, request: Request):
        with factory.begin() as db:
            user = actor(db, request, organization_id, licensed=False)
            project_access(db, organization_id, user.id, project_id, manage=True)
            # Only existing active company colleagues can be invited to a project.
            rows = db.execute(
                select(User, Membership)
                .join(Membership, Membership.user_id == User.id)
                .where(
                    Membership.organization_id == organization_id,
                    Membership.active.is_(True),
                    User.active.is_(True),
                )
            ).all()
            return {
                "members": [
                    {
                        "user_id": person.id,
                        "display_name": person.display_name,
                        "role": membership.role
                        if (membership := db.get(ProjectMember, (project_id, person.id)))
                        else "owner"
                        if person.id == user.id
                        else None,
                    }
                    for person, _ in rows
                ]
            }

    @router.put(prefix + "/members")
    def invite(organization_id: str, project_id: str, request: Request, body: MemberInput):
        with factory.begin() as db:
            user = actor(db, request, organization_id)
            project = project_access(db, organization_id, user.id, project_id, manage=True)
            colleague = db.get(Membership, (organization_id, str(body.user_id)))
            if not colleague or not colleague.active or not db.get(User, colleague.user_id).active:
                raise HTTPException(404, "resource_not_found")
            if colleague.user_id == project.owner_id:
                raise HTTPException(409, "project_owner_role_fixed")
            row = db.get(ProjectMember, (project_id, colleague.user_id))
            if row:
                row.role = body.role
            else:
                db.add(
                    ProjectMember(
                        project_id=project_id,
                        user_id=colleague.user_id,
                        organization_id=organization_id,
                        role=body.role,
                    )
                )
            return {"user_id": colleague.user_id, "role": body.role}

    @router.delete(prefix + "/members/{user_id}", status_code=204)
    def revoke(organization_id: str, project_id: str, user_id: str, request: Request):
        with factory.begin() as db:
            user = actor(db, request, organization_id)
            project_access(db, organization_id, user.id, project_id, manage=True)
            row = db.get(ProjectMember, (project_id, user_id))
            if row:
                db.delete(row)

    @router.get(prefix + "/entries")
    def entries(organization_id: str, project_id: str, request: Request):
        with factory.begin() as db:
            user = actor(db, request, organization_id, licensed=False)
            project_access(db, organization_id, user.id, project_id)
            rows = db.scalars(
                select(ProjectEntry)
                .where(ProjectEntry.project_id == project_id, ProjectEntry.organization_id == organization_id)
                .order_by(ProjectEntry.created_at.desc(), ProjectEntry.id)
            ).all()
            return {"entries": [entry_view(item) for item in rows]}

    @router.post(prefix + "/entries", status_code=201)
    def publish(organization_id: str, project_id: str, request: Request, body: EntryInput):
        with factory.begin() as db:
            user = actor(db, request, organization_id)
            project_access(db, organization_id, user.id, project_id, write=True)
            identifier = str(body.request_id or uuid4())
            existing = db.get(ProjectEntry, identifier)
            if existing:
                if (
                    existing.organization_id,
                    existing.owner_id,
                    existing.project_id,
                    existing.title,
                    existing.content,
                    existing.kind,
                ) != (organization_id, user.id, project_id, body.title.strip(), body.content, body.kind):
                    raise HTTPException(409, "project_publication_conflict")
                return entry_view(existing)
            item = ProjectEntry(
                id=identifier,
                organization_id=organization_id,
                owner_id=user.id,
                project_id=project_id,
                title=body.title.strip(),
                content=body.content,
                kind=body.kind,
            )
            db.add(item)
            db.flush()
            return entry_view(item)

    def editable(db, user, organization_id, project_id, entry_id):
        project = project_access(db, organization_id, user.id, project_id, write=True)
        item = db.scalar(
            select(ProjectEntry)
            .where(
                ProjectEntry.id == entry_id,
                ProjectEntry.organization_id == organization_id,
                ProjectEntry.project_id == project_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if not item:
            raise HTTPException(404, "resource_not_found")
        if user.id not in (project.owner_id, item.owner_id):
            raise HTTPException(403, "project_entry_owner_required")
        return item

    @router.put(prefix + "/entries/{entry_id}")
    def update(organization_id: str, project_id: str, entry_id: str, request: Request, body: EntryInput):
        with factory.begin() as db:
            user = actor(db, request, organization_id)
            item = editable(db, user, organization_id, project_id, entry_id)
            if item.version != body.version:
                raise HTTPException(409, "project_entry_changed")
            item.title, item.content, item.version = body.title.strip(), body.content, item.version + 1
            return entry_view(item)

    @router.delete(prefix + "/entries/{entry_id}", status_code=204)
    def delete(organization_id: str, project_id: str, entry_id: str, request: Request):
        with factory.begin() as db:
            user = actor(db, request, organization_id)
            db.delete(editable(db, user, organization_id, project_id, entry_id))
