"""Owner and conversation checks are repeated for every attachment operation."""

import base64
import json
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import Field
from sqlalchemy import and_, or_, select

from .file_access import file_access, unpublished_file
from .models import Conversation, ProjectFile, WorkspaceFile
from .project_access import project_access
from .schemas import Input
from .work_settings import source_allowed
from .workspace_files import VersionInput, add_version, decode_upload, file_store, file_view, version_record


class FileRequest(Input):
    operation: Literal["list", "read", "save"]
    file_id: UUID | None = None
    version: int | None = Field(default=None, ge=1)
    expected_version: int | None = Field(default=None, ge=1)
    content_base64: str | None = Field(default=None, max_length=6990508)


def access_file(db, settings, turn, payload):
    body = FileRequest.model_validate(payload)
    conversation = db.get(Conversation, turn.conversation_id)
    private = and_(
        WorkspaceFile.owner_id == turn.owner_id,
        WorkspaceFile.conversation_id == turn.conversation_id,
        unpublished_file(),
    )
    scopes = [private]
    if conversation.context_project_id and source_allowed(conversation, "project"):
        try:
            project_access(db, turn.organization_id, turn.owner_id, conversation.context_project_id)
        except HTTPException as error:
            if error.status_code != 404:
                raise
        else:
            scopes.append(
                select(ProjectFile.id)
                .where(
                    ProjectFile.file_id == WorkspaceFile.id,
                    ProjectFile.organization_id == turn.organization_id,
                    ProjectFile.project_id == conversation.context_project_id,
                )
                .exists()
            )
    query = select(WorkspaceFile).where(
        WorkspaceFile.organization_id == turn.organization_id,
        or_(*scopes),
    )
    if body.operation == "list":
        return {
            "files": [
                file_view(item, db) for item in db.scalars(query.order_by(WorkspaceFile.created_at)).all()
            ]
        }
    item = db.scalar(query.where(WorkspaceFile.id == str(body.file_id)))
    if item is None:
        raise HTTPException(404, "resource_not_found")
    item = file_access(db, turn.organization_id, turn.owner_id, item.id, write=body.operation == "save")
    store = file_store(settings)
    if body.operation == "read":
        version = version_record(db, item, body.version or item.version)
        # The broker frame also carries up to 7 MB of base64. Bound escaped JSON,
        # including CJK and emoji, so a valid attachment cannot overflow the frame.
        passages = []
        remaining = 200000
        for passage in version.analysis_pages or []:
            size = len(json.dumps(passage).encode("utf-8"))
            if size > remaining:
                break
            passages.append(passage)
            remaining -= size
        return {
            "files": [
                {
                    "id": item.id,
                    "name": item.filename,
                    "version": version.version,
                    "size": version.size,
                    "source": "conversation_attachment",
                }
            ],
            "analysis_status": version.analysis_status,
            "passages": passages,
            "passages_partial": len(passages) < len(version.analysis_pages or []),
            "content_base64": base64.b64encode(store.get(version.object_key)).decode("ascii"),
        }
    if body.expected_version is None or body.content_base64 is None:
        raise HTTPException(422, "document_version_required")
    content, _ = decode_upload(
        VersionInput(
            filename=item.filename, content_base64=body.content_base64, expected_version=body.expected_version
        )
    )
    add_version(db, store, item, content, body.expected_version)
    return file_view(item)
