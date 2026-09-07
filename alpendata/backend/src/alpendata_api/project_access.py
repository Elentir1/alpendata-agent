"""Project access never confers access to a member's private conversations."""

from fastapi import HTTPException
from sqlalchemy import or_, select

from .models import Project, ProjectMember


def accessible_projects(user_id):
    return or_(
        Project.owner_id == user_id,
        select(ProjectMember.user_id)
        .where(
            ProjectMember.project_id == Project.id,
            ProjectMember.organization_id == Project.organization_id,
            ProjectMember.user_id == user_id,
        )
        .exists(),
    )


def project_role(db, project, user_id):
    if project.owner_id == user_id:
        return "owner"
    membership = db.get(ProjectMember, (project.id, user_id))
    return membership.role if membership else None


def conversation_context_access(db, conversation):
    """A cached project brief cannot authorize future work after membership revocation."""
    if conversation.context_project_id:
        try:
            project_access(
                db, conversation.organization_id, conversation.owner_id, conversation.context_project_id
            )
        except HTTPException:
            raise HTTPException(403, "project_context_revoked") from None


def project_access(db, organization_id, user_id, project_id, *, write=False, manage=False):
    query = select(Project).where(
        Project.id == project_id, Project.organization_id == organization_id, accessible_projects(user_id)
    )
    if write or manage:
        query = query.with_for_update().execution_options(populate_existing=True)
    item = db.scalar(query)
    if item is None:
        raise HTTPException(404, "resource_not_found")
    role = project_role(db, item, user_id)
    if (manage and role != "owner") or (write and role == "reader"):
        raise HTTPException(403, "project_contributor_required")
    return item
