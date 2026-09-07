"""Owner-scoped project organization; project grouping never grants access."""

from fastapi import Request
from pydantic import Field
from sqlalchemy import select

from .models import Project
from .project_access import accessible_projects, project_access, project_role
from .schemas import Input


class ProjectInput(Input):
    name: str = Field(min_length=1, max_length=160, pattern=r"\S")
    instructions: str = Field(default="", max_length=8000)


def project_view(item, role="owner"):
    return {
        "id": item.id,
        "name": item.name,
        "instructions": item.instructions,
        "owner_id": item.owner_id,
        "role": role,
    }


def attach_project_routes(router, factory, actor):
    prefix = "/api/organizations/{organization_id}/chat/projects"

    @router.get(prefix)
    def projects(organization_id: str, request: Request):
        with factory.begin() as db:
            user = actor(db, request, organization_id, licensed=False)
            rows = db.scalars(
                select(Project)
                .where(
                    Project.organization_id == organization_id,
                    accessible_projects(user.id),
                )
                .order_by(Project.name, Project.id)
            ).all()
            return {"projects": [project_view(item, project_role(db, item, user.id)) for item in rows]}

    @router.post(prefix, status_code=201)
    def create(organization_id: str, request: Request, body: ProjectInput):
        with factory.begin() as db:
            user = actor(db, request, organization_id)
            item = Project(
                organization_id=organization_id,
                owner_id=user.id,
                name=body.name.strip(),
                instructions=body.instructions.strip(),
            )
            db.add(item)
            db.flush()
            return project_view(item)

    @router.put(prefix + "/{project_id}")
    def update(organization_id: str, project_id: str, request: Request, body: ProjectInput):
        with factory.begin() as db:
            user = actor(db, request, organization_id)
            item = project_access(db, organization_id, user.id, project_id, write=True)
            item.name, item.instructions = body.name.strip(), body.instructions.strip()
            return project_view(item, project_role(db, item, user.id))

    from .project_sharing import attach_sharing_routes

    attach_sharing_routes(router, factory, actor)
