"""A publication grants access to its copy, never its original or conversation."""

from fastapi import HTTPException
from sqlalchemy import select

from .access import visible_resource
from .models import ProjectFile, WorkspaceFile
from .project_access import project_access


def publication(db, file_id):
    return db.scalar(select(ProjectFile).where(ProjectFile.file_id == file_id))


def unpublished_file():
    return ~select(ProjectFile.id).where(ProjectFile.file_id == WorkspaceFile.id).exists()


def file_access(db, organization_id, user_id, file_id, *, write=False):
    query = select(WorkspaceFile).where(
        WorkspaceFile.id == file_id, WorkspaceFile.organization_id == organization_id
    )
    item = db.scalar(query)
    if item is None:
        raise HTTPException(404, "resource_not_found")
    shared = publication(db, item.id)
    if shared:
        project_access(db, organization_id, user_id, shared.project_id, write=write)
    elif item.owner_id != user_id:
        raise HTTPException(404, "resource_not_found")
    else:
        visible_resource(db, item)
    if write:
        item = db.scalar(query.with_for_update().execution_options(populate_existing=True))
    return item
