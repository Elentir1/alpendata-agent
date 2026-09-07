"""Private attachments and immutable Office versions, shared only by explicit publication."""

import base64
import binascii
import unicodedata
from pathlib import PurePosixPath
from urllib.parse import quote
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import Field
from sqlalchemy import func, select

from .access import member, owned
from .artifacts import ArtifactInput, validate_document
from .auth import authenticate, request_authorization
from .connections import lock_member
from .file_access import file_access, unpublished_file
from .file_store import LIMIT, FileStore, FileStoreSettings
from .models import Artifact, Conversation, FileVersion, ProjectFile, WorkspaceFile
from .project_access import project_access, project_role
from .schemas import Input


class UploadInput(ArtifactInput):
    request_id: UUID


class PublishFileInput(Input):
    request_id: UUID
    file_id: UUID
    version: int = Field(ge=1)


class VersionInput(ArtifactInput):
    expected_version: int = Field(ge=1)


class RestoreInput(Input):
    expected_version: int = Field(ge=1)
    source_version: int = Field(ge=1)


def file_store(settings):
    configured = settings.files
    if configured is None and settings.runtime:
        configured = FileStoreSettings(root=settings.runtime.state_root / "objects")
    if configured is None:
        raise HTTPException(503, "document_storage_not_configured")
    return FileStore(configured)


def file_view(item, db=None):
    result = {key: getattr(item, key) for key in ("id", "filename", "media_type", "version", "created_at")}
    if db is not None:
        result["analysis_status"] = version_record(db, item, item.version).analysis_status
    return result


def decode_upload(body):
    try:
        content = base64.b64decode(body.content_base64, validate=True)
    except (ValueError, binascii.Error):
        raise HTTPException(400, "document_format_invalid") from None
    extension = PurePosixPath(body.filename).suffix.lower()
    if extension in {".docx", ".xlsx", ".pptx", ".pdf"}:
        return content, validate_document(body.filename, content)
    if (
        body.filename.startswith(".")
        or any(c in body.filename for c in '/\\:<>"|?*')
        or any(unicodedata.category(c).startswith("C") for c in body.filename)
    ):
        raise HTTPException(400, "document_filename_invalid")
    if not content or len(content) > LIMIT:
        raise HTTPException(413, "document_too_large")
    if extension in {".txt", ".md", ".csv"}:
        try:
            content.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise HTTPException(400, "document_encoding_unsupported") from None
        return content, "text/plain"
    signatures = {
        ".png": (b"\x89PNG\r\n\x1a\n", "image/png"),
        ".jpg": (b"\xff\xd8\xff", "image/jpeg"),
        ".jpeg": (b"\xff\xd8\xff", "image/jpeg"),
    }
    if extension in signatures and content.startswith(signatures[extension][0]):
        return content, signatures[extension][1]
    raise HTTPException(400, "document_format_unsupported")


def version_record(db, item, version):
    row = db.scalar(
        select(FileVersion).where(
            FileVersion.file_id == item.id,
            FileVersion.organization_id == item.organization_id,
            FileVersion.owner_id == item.owner_id,
            FileVersion.version == version,
        )
    )
    if row is None:
        raise HTTPException(404, "resource_not_found")
    return row


def add_version(db, store, item, content, expected_version=None):
    stored_bytes = db.scalar(
        select(func.coalesce(func.sum(FileVersion.size), 0)).where(
            FileVersion.organization_id == item.organization_id, FileVersion.owner_id == item.owner_id
        )
    )
    if stored_bytes + len(content) > 500 * 1024 * 1024:
        raise HTTPException(413, "document_storage_quota_reached")
    if expected_version is not None:
        if item.version != expected_version:
            raise HTTPException(409, "document_version_changed")
        item.version += 1
    key, digest = store.put(item.organization_id, item.owner_id, content)
    row = FileVersion(
        organization_id=item.organization_id,
        owner_id=item.owner_id,
        file_id=item.id,
        version=item.version,
        object_key=key,
        sha256=digest,
        size=len(content),
    )
    db.add(row)
    db.flush()
    return row


def files_router(settings, factory):
    router = APIRouter()
    root = "/api/organizations/{organization_id}"
    prefix = root + "/chat/conversations/{conversation_id}/files"

    def actor(db, request, organization_id, write=False):
        user = authenticate(db, request_authorization(request, settings))
        if write:
            lock_member(db, user, organization_id)
        else:
            member(db, user, organization_id, licensed=False)
        return user

    @router.get(prefix)
    def listing(organization_id: str, conversation_id: str, request: Request):
        with factory() as db:
            user = actor(db, request, organization_id)
            owned(db, Conversation, organization_id, user.id, conversation_id)
            rows = db.scalars(
                select(WorkspaceFile)
                .where(
                    WorkspaceFile.conversation_id == conversation_id,
                    WorkspaceFile.organization_id == organization_id,
                    WorkspaceFile.owner_id == user.id,
                    unpublished_file(),
                )
                .order_by(WorkspaceFile.created_at, WorkspaceFile.id)
            ).all()
            return {
                "files": [file_view(row, db) for row in rows],
                "max_bytes": LIMIT,
                "editor_available": bool(settings.office_origin and settings.office_secret),
            }

    @router.post(prefix, status_code=201)
    def upload(organization_id: str, conversation_id: str, request: Request, body: UploadInput):
        with factory.begin() as db:
            user = actor(db, request, organization_id, write=True)
            owned(db, Conversation, organization_id, user.id, conversation_id)
            content, media_type = decode_upload(body)
            existing = db.get(WorkspaceFile, str(body.request_id))
            if existing:
                if (
                    existing.organization_id,
                    existing.owner_id,
                    existing.conversation_id,
                    existing.filename,
                ) != (organization_id, user.id, conversation_id, body.filename):
                    raise HTTPException(409, "document_request_conflict")
                import hashlib

                if version_record(db, existing, 1).sha256 != hashlib.sha256(content).hexdigest():
                    raise HTTPException(409, "document_request_conflict")
                return file_view(existing)
            item = WorkspaceFile(
                id=str(body.request_id),
                organization_id=organization_id,
                owner_id=user.id,
                conversation_id=conversation_id,
                filename=body.filename,
                media_type=media_type,
            )
            db.add(item)
            db.flush()
            add_version(db, file_store(settings), item, content)
            return file_view(item)

    @router.post(prefix + "/from-artifact", status_code=201)
    def from_artifact(organization_id: str, conversation_id: str, request: Request, body: dict):
        with factory.begin() as db:
            user = actor(db, request, organization_id, write=True)
            owned(db, Conversation, organization_id, user.id, conversation_id)
            source = owned(db, Artifact, organization_id, user.id, str(body.get("artifact_id", "")))
            identifier = str(
                uuid5(
                    NAMESPACE_URL,
                    f"alpendata://artifact/{organization_id}/{user.id}/{conversation_id}/{source.id}",
                )
            )
            existing = db.get(WorkspaceFile, identifier)
            if existing:
                import hashlib

                if (
                    existing.organization_id,
                    existing.owner_id,
                    existing.conversation_id,
                    existing.filename,
                ) != (organization_id, user.id, conversation_id, source.filename) or version_record(
                    db, existing, 1
                ).sha256 != hashlib.sha256(source.content).hexdigest():
                    raise HTTPException(409, "document_request_conflict")
                return file_view(existing)
            item = WorkspaceFile(
                id=identifier,
                organization_id=organization_id,
                owner_id=user.id,
                conversation_id=conversation_id,
                filename=source.filename,
                media_type=source.media_type,
            )
            db.add(item)
            db.flush()
            add_version(db, file_store(settings), item, source.content)
            return file_view(item)

    projects_path = root + "/chat/projects/{project_id}/files"

    @router.get(projects_path)
    def project_files(organization_id: str, project_id: str, request: Request):
        with factory() as db:
            user = actor(db, request, organization_id)
            project = project_access(db, organization_id, user.id, project_id)
            rows = db.scalars(
                select(WorkspaceFile)
                .join(ProjectFile, ProjectFile.file_id == WorkspaceFile.id)
                .where(ProjectFile.project_id == project_id, ProjectFile.organization_id == organization_id)
                .order_by(WorkspaceFile.created_at, WorkspaceFile.id)
            ).all()
            return {
                "files": [file_view(item, db) for item in rows],
                "writable": project_role(db, project, user.id) != "reader",
                "max_bytes": LIMIT,
                "editor_available": bool(settings.office_origin and settings.office_secret),
            }

    @router.post(projects_path, status_code=201)
    def publish_file(organization_id: str, project_id: str, request: Request, body: PublishFileInput):
        with factory.begin() as db:
            user = actor(db, request, organization_id, write=True)
            project_access(db, organization_id, user.id, project_id, write=True)
            identifier = str(body.request_id)
            existing = db.get(ProjectFile, identifier)
            if existing:
                if (
                    existing.organization_id,
                    existing.owner_id,
                    existing.project_id,
                    existing.source_file_id,
                    existing.source_version,
                ) != (organization_id, user.id, project_id, str(body.file_id), body.version):
                    raise HTTPException(409, "project_publication_conflict")
                return file_view(file_access(db, organization_id, user.id, existing.file_id), db)
            # Publishing an existing personal attachment is explicit and version-specific.
            source = owned(db, WorkspaceFile, organization_id, user.id, str(body.file_id))
            if not db.scalar(
                select(WorkspaceFile.id).where(WorkspaceFile.id == source.id, unpublished_file())
            ):
                raise HTTPException(409, "document_personal_source_required")
            original = version_record(db, source, body.version)
            store = file_store(settings)
            item = WorkspaceFile(
                organization_id=organization_id,
                owner_id=user.id,
                conversation_id=source.conversation_id,
                filename=source.filename,
                media_type=source.media_type,
            )
            db.add(item)
            db.flush()
            copied = add_version(db, store, item, store.get(original.object_key))
            if original.analysis_status in {
                "ready",
                "partial",
                "no_text",
                "vision_required",
                "password_required",
            }:
                copied.analysis_status, copied.analysis_text, copied.analysis_pages = (
                    original.analysis_status,
                    original.analysis_text,
                    original.analysis_pages,
                )
            db.add(
                ProjectFile(
                    id=identifier,
                    organization_id=organization_id,
                    owner_id=user.id,
                    project_id=project_id,
                    file_id=item.id,
                    source_file_id=source.id,
                    source_version=body.version,
                )
            )
            db.flush()
            return file_view(item, db)

    @router.get(root + "/files/{file_id}/versions")
    def versions(organization_id: str, file_id: str, request: Request):
        with factory() as db:
            user = actor(db, request, organization_id)
            item = file_access(db, organization_id, user.id, file_id)
            rows = db.scalars(
                select(FileVersion).where(FileVersion.file_id == item.id).order_by(FileVersion.version.desc())
            ).all()
            return {
                "file": file_view(item, db),
                "versions": [
                    {
                        "version": row.version,
                        "size": row.size,
                        "sha256": row.sha256,
                        "created_at": row.created_at,
                    }
                    for row in rows
                ],
            }

    @router.get(root + "/files/{file_id}/versions/{version}/content")
    def download(organization_id: str, file_id: str, version: int, request: Request):
        with factory() as db:
            user = actor(db, request, organization_id)
            item = file_access(db, organization_id, user.id, file_id)
            content = file_store(settings).get(version_record(db, item, version).object_key)
            return Response(
                content,
                media_type=item.media_type,
                headers={
                    "Content-Disposition": "attachment; filename*=UTF-8''" + quote(item.filename, safe=""),
                    "Content-Security-Policy": "sandbox; default-src 'none'",
                },
            )

    @router.get(root + "/files/{file_id}/versions/{version}/passages")
    def passages(organization_id: str, file_id: str, version: int, request: Request):
        with factory() as db:
            user = actor(db, request, organization_id)
            item = file_access(db, organization_id, user.id, file_id)
            row = version_record(db, item, version)
            return {
                "file": file_view(item),
                "version": row.version,
                "status": row.analysis_status,
                "passages": row.analysis_pages or [],
            }

    @router.post(root + "/files/{file_id}/versions", status_code=201)
    def save(organization_id: str, file_id: str, request: Request, body: VersionInput):
        with factory.begin() as db:
            user = actor(db, request, organization_id, write=True)
            item = file_access(db, organization_id, user.id, file_id, write=True)
            content, media_type = decode_upload(body)
            if body.filename != item.filename or media_type != item.media_type:
                raise HTTPException(422, "document_format_changed")
            add_version(db, file_store(settings), item, content, body.expected_version)
            return file_view(item)

    @router.post(root + "/files/{file_id}/restore")
    def restore(organization_id: str, file_id: str, request: Request, body: RestoreInput):
        with factory.begin() as db:
            user = actor(db, request, organization_id, write=True)
            item = file_access(db, organization_id, user.id, file_id, write=True)
            store = file_store(settings)
            content = store.get(version_record(db, item, body.source_version).object_key)
            add_version(db, store, item, content, body.expected_version)
            return file_view(item)

    from .document_comparison import attach_comparison_route

    attach_comparison_route(router, factory, actor)
    return router
