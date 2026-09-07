"""Reviewed kDrive writes with conditional requests and persistent receipts."""

from urllib.parse import quote, unquote, urlsplit
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field
from sqlalchemy import select

from .access import owned
from .auth import authenticate, request_authorization
from .connections import lock_member
from .infomaniak import InfomaniakReader
from .infomaniak_dav import DAV, decode_path, drive_origin, opaque_path, safe_url
from .models import Artifact, SharePointSave, now
from .schemas import Input
from .sharepoint_saves import ConfirmInput, personal_save, save_view


class FolderInput(Input):
    folder_id: str = Field(default="Lw", min_length=1, max_length=512, pattern=r"^[A-Za-z0-9_-]+$")


class PrepareInput(FolderInput):
    request_id: UUID
    artifact_id: UUID


def folder_path(credentials, identifier):
    return (
        urlsplit(safe_url(drive_origin(credentials["drive_id"]), decode_path(identifier))).path.rstrip("/")
        + "/"
    )


def metadata(dav, credentials, path, missing=False):
    origin = drive_origin(credentials["drive_id"])
    tree = dav.properties(credentials, origin, path, missing=missing)
    if tree is None:
        return None
    for row in tree.findall("{" + DAV + "}response"):
        href = urlsplit(safe_url(origin, row.findtext("{" + DAV + "}href", ""))).path
        if href.rstrip("/") == path.rstrip("/"):
            return {
                "path": href,
                "folder": row.find(".//{" + DAV + "}collection") is not None,
                "etag": row.findtext(".//{" + DAV + "}getetag"),
            }
    raise HTTPException(502, "infomaniak_response_invalid")


def kdrive_router(settings, factory):
    router = APIRouter()
    root = "/api/organizations/{organization_id}/kdrive"
    reader = InfomaniakReader(settings, factory)

    def actor(db, request, organization_id, licensed=True):
        user = authenticate(db, request_authorization(request, settings))
        lock_member(db, user, organization_id, licensed=licensed)
        return user

    def execute(organization_id, request, perform):
        def checked(_transport, credentials):
            if not credentials.get("files"):
                raise HTTPException(409, "infomaniak_reconnect_required")
            return perform(reader.dav, credentials["files"])

        return reader.execute(
            organization_id, lambda db: actor(db, request, organization_id), "files_write", checked
        )

    @router.post(root + "/folders")
    def folders(organization_id: str, request: Request, body: FolderInput):
        def browse(dav, credentials):
            path = folder_path(credentials, body.folder_id)
            origin = drive_origin(credentials["drive_id"])
            tree = dav.properties(credentials, origin, path, "1")
            rows = tree.findall("{" + DAV + "}response")
            children = []
            for row in rows[:500]:
                href = urlsplit(safe_url(origin, row.findtext("{" + DAV + "}href", ""))).path
                if (
                    href.rstrip("/") != path.rstrip("/")
                    and row.find(".//{" + DAV + "}collection") is not None
                ):
                    identifier = opaque_path(href)
                    if len(identifier) <= 512:
                        children.append(
                            {"id": identifier, "name": unquote(href.rstrip("/").rsplit("/", 1)[-1])}
                        )
            return {"path": unquote(path), "folders": children, "partial": len(rows) > 500}

        return execute(organization_id, request, browse)

    @router.post(root + "/saves", status_code=201)
    def prepare(organization_id: str, request: Request, body: PrepareInput):
        with factory.begin() as db:
            user = actor(db, request, organization_id)
            source = owned(db, Artifact, organization_id, user.id, str(body.artifact_id))
            filename = source.filename
            existing = db.get(SharePointSave, str(body.request_id))
            if existing:
                if (
                    existing.organization_id,
                    existing.owner_id,
                    existing.provider,
                    existing.artifact_id,
                    existing.folder_id,
                ) != (organization_id, user.id, "infomaniak", source.id, body.folder_id):
                    raise HTTPException(409, "document_request_conflict")
                return save_view(existing)

        def inspect(dav, credentials):
            path = folder_path(credentials, body.folder_id)
            folder = metadata(dav, credentials, path)
            if not folder["folder"]:
                raise HTTPException(422, "document_folder_required")
            current = metadata(dav, credentials, path + quote(filename, safe=""), missing=True)
            if current and (current["folder"] or not current["etag"]):
                raise HTTPException(409, "document_destination_unsupported")
            return str(credentials["drive_id"]), path, current

        drive, path, current = execute(organization_id, request, inspect)
        with factory.begin() as db:
            user = actor(db, request, organization_id)
            existing = db.get(SharePointSave, str(body.request_id))
            if existing:
                if (
                    existing.organization_id,
                    existing.owner_id,
                    existing.provider,
                    existing.artifact_id,
                    existing.folder_id,
                ) != (organization_id, user.id, "infomaniak", str(body.artifact_id), body.folder_id):
                    raise HTTPException(409, "document_request_conflict")
                return save_view(existing)
            row = SharePointSave(
                id=str(body.request_id),
                organization_id=organization_id,
                owner_id=user.id,
                provider="infomaniak",
                artifact_id=str(body.artifact_id),
                drive_id=drive,
                folder_id=body.folder_id,
                folder_name=unquote(path),
                filename=filename,
                existing_id="existing" if current else None,
                existing_etag=current["etag"] if current else None,
                expires_at=now() + 900,
            )
            db.add(row)
            db.flush()
            return save_view(row)

    @router.get(root + "/saves/{save_id}")
    def status(organization_id: str, save_id: str, request: Request):
        with factory.begin() as db:
            user = actor(db, request, organization_id, licensed=False)
            return save_view(personal_save(db, organization_id, user.id, save_id, "infomaniak"))

    @router.post(root + "/saves/{save_id}/confirm")
    def confirm(organization_id: str, save_id: str, request: Request, body: ConfirmInput):
        with factory.begin() as db:
            user = actor(db, request, organization_id)
            row = personal_save(db, organization_id, user.id, save_id, "infomaniak")
            if row.status != "review":
                return save_view(row)
            if row.expires_at <= now():
                raise HTTPException(409, "document_review_expired")
            if bool(row.existing_id) != body.replace_existing:
                raise HTTPException(409, "document_replacement_confirmation_required")
            unresolved = db.scalar(
                select(SharePointSave.id).where(
                    SharePointSave.organization_id == organization_id,
                    SharePointSave.owner_id == user.id,
                    SharePointSave.provider == "infomaniak",
                    SharePointSave.drive_id == row.drive_id,
                    SharePointSave.folder_id == row.folder_id,
                    SharePointSave.filename == row.filename,
                    SharePointSave.status.in_(("running", "unknown")),
                )
            )
            if unresolved:
                raise HTTPException(409, "document_save_unresolved")
            source = owned(db, Artifact, organization_id, user.id, row.artifact_id)
            content, media_type = source.content, source.media_type
            row.status, row.started_at = "running", now()
            db.flush()
            db.expunge(row)

        def write(dav, credentials):
            if str(credentials["drive_id"]) != row.drive_id:
                raise HTTPException(409, "document_connection_changed")
            path = folder_path(credentials, row.folder_id) + quote(row.filename, safe="")
            condition = {"If-Match": row.existing_etag} if row.existing_id else {"If-None-Match": "*"}
            _, headers = dav.request(
                credentials,
                drive_origin(row.drive_id),
                "PUT",
                path,
                content,
                {**condition, "Content-Type": media_type},
                statuses=(200, 201, 204),
            )
            return {
                "item_id": opaque_path(path),
                "name": row.filename,
                "etag": headers.get("ETag") or headers.get("etag"),
                "url": "https://ksuite.infomaniak.com/",
            }

        try:
            result, error, state = execute(organization_id, request, write), None, "completed"
        except HTTPException as failure:
            result, error = None, failure.detail
            state = "unknown" if error == "infomaniak_write_unknown" else "failed"
        with factory.begin() as db:
            item = db.get(SharePointSave, save_id)
            item.status, item.result, item.error_code, item.finished_at = state, result, error, now()
        with factory.begin() as db:
            user = actor(db, request, organization_id, licensed=False)
            return save_view(personal_save(db, organization_id, user.id, save_id, "infomaniak"))

    return router
