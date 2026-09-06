"""Personal, durable document-save reviews. Only a browser confirmation writes."""

import base64
import hashlib
from pathlib import PurePosixPath

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field
from sqlalchemy import select

from .access import owned
from .artifacts import validate_document
from .auth import authenticate, request_authorization
from .connections import MicrosoftReader, SearchInput, lock_member
from .graph import GraphError
from .graph_documents import FileInput, content_download
from .graph_save import browse_folder, inspect_destination, save_document, search_folders
from .models import Artifact, SharePointSave, now
from .schemas import Input

PREFIX = "/api/organizations/{organization_id}/sharepoint"


class ReviewInput(FileInput):
    artifact_id: str = Field(min_length=36, max_length=36)
    filename: str = Field(min_length=1, max_length=180)


class ConfirmInput(Input):
    replace_existing: bool = False


def save_view(item):
    result = {
        key: getattr(item, key)
        for key in (
            "id",
            "artifact_id",
            "drive_id",
            "folder_id",
            "folder_name",
            "folder_url",
            "filename",
            "status",
            "error_code",
            "result",
            "created_at",
            "expires_at",
            "started_at",
            "finished_at",
        )
    }
    result["replaces_existing"] = item.existing_id is not None
    if item.status == "running" and item.started_at + 180 < now():
        result["status"], result["error_code"] = "unknown", "sharepoint_save_unknown"
    return result


def sharepoint_router(settings, factory, provider=None, graph=None):
    router = APIRouter()
    microsoft = MicrosoftReader(settings, factory, provider, graph)

    def actor(db, request, organization_id, *, licensed=True):
        user = authenticate(db, request_authorization(request, settings))
        lock_member(db, user, organization_id, licensed=licensed)
        return user

    @router.post(PREFIX + "/folders/search")
    def search(organization_id: str, request: Request, body: SearchInput):
        return microsoft.execute(
            organization_id,
            lambda db: actor(db, request, organization_id),
            "files_write",
            lambda graph, token: search_folders(graph, token, body.query),
        )

    @router.post(PREFIX + "/folders/browse")
    def browse(organization_id: str, request: Request, body: FileInput):
        return microsoft.execute(
            organization_id,
            lambda db: actor(db, request, organization_id),
            "files_write",
            lambda graph, token: browse_folder(graph, token, body.drive_id, body.item_id),
        )

    @router.get(PREFIX + "/saves")
    def history(organization_id: str, artifact_id: str, request: Request):
        with factory.begin() as db:
            user = actor(db, request, organization_id, licensed=False)
            owned(db, Artifact, organization_id, user.id, artifact_id)
            return {
                "saves": [
                    save_view(item)
                    for item in db.scalars(
                        select(SharePointSave)
                        .where(
                            SharePointSave.organization_id == organization_id,
                            SharePointSave.owner_id == user.id,
                            SharePointSave.artifact_id == artifact_id,
                        )
                        .order_by(SharePointSave.created_at.desc(), SharePointSave.id)
                        .limit(30)
                    )
                ]
            }

    @router.post(PREFIX + "/saves", status_code=201)
    def prepare(organization_id: str, request: Request, body: ReviewInput):
        with factory.begin() as db:
            user = actor(db, request, organization_id)
            artifact = owned(db, Artifact, organization_id, user.id, body.artifact_id)
            validate_document(body.filename, artifact.content)
            if PurePosixPath(body.filename).suffix.lower() != PurePosixPath(artifact.filename).suffix.lower():
                raise HTTPException(400, "document_format_invalid")
        folder, existing = microsoft.execute(
            organization_id,
            lambda db: actor(db, request, organization_id),
            "files_write",
            lambda graph, token: inspect_destination(
                graph, token, body.drive_id, body.item_id, body.filename
            ),
        )
        with factory.begin() as db:
            user = actor(db, request, organization_id)
            owned(db, Artifact, organization_id, user.id, body.artifact_id)
            unresolved = db.scalar(
                select(SharePointSave).where(
                    SharePointSave.organization_id == organization_id,
                    SharePointSave.owner_id == user.id,
                    SharePointSave.drive_id == body.drive_id,
                    SharePointSave.folder_id == body.item_id,
                    SharePointSave.filename == body.filename,
                    SharePointSave.status.in_(("running", "unknown")),
                )
            )
            if unresolved:
                raise HTTPException(409, "sharepoint_save_unresolved")
            item = SharePointSave(
                organization_id=organization_id,
                owner_id=user.id,
                artifact_id=body.artifact_id,
                drive_id=body.drive_id,
                folder_id=body.item_id,
                folder_name=folder["name"],
                folder_url=folder["url"],
                filename=body.filename,
                existing_id=existing["id"] if existing else None,
                existing_etag=existing["eTag"] if existing else None,
                expires_at=now() + 900,
            )
            db.add(item)
            db.flush()
            return save_view(item)

    @router.get(PREFIX + "/saves/{save_id}")
    def status(organization_id: str, save_id: str, request: Request):
        with factory.begin() as db:
            user = actor(db, request, organization_id, licensed=False)
            return save_view(owned(db, SharePointSave, organization_id, user.id, save_id))

    @router.post(PREFIX + "/saves/{save_id}/confirm")
    def confirm(organization_id: str, save_id: str, request: Request, body: ConfirmInput):
        with factory.begin() as db:
            user = actor(db, request, organization_id)
            item = owned(db, SharePointSave, organization_id, user.id, save_id)
            if item.status != "review":
                return save_view(item)
            if item.expires_at <= now():
                raise HTTPException(409, "sharepoint_review_expired")
            if bool(item.existing_id) != body.replace_existing:
                raise HTTPException(409, "sharepoint_replacement_confirmation_required")
            # Serialize saves to a destination within the owner's membership lock.
            unresolved = db.scalar(
                select(SharePointSave.id).where(
                    SharePointSave.organization_id == organization_id,
                    SharePointSave.owner_id == user.id,
                    SharePointSave.drive_id == item.drive_id,
                    SharePointSave.folder_id == item.folder_id,
                    SharePointSave.filename == item.filename,
                    SharePointSave.status.in_(("running", "unknown")),
                )
            )
            if unresolved:
                raise HTTPException(409, "sharepoint_save_unresolved")
            artifact = owned(db, Artifact, organization_id, user.id, item.artifact_id)
            content, media_type = artifact.content, artifact.media_type
            item.status, item.started_at = "running", now()
            db.flush()
            db.expunge(item)
        # The durable running receipt is committed before any external mutation.
        # A process crash or lost response never makes this confirmation retryable.
        try:
            result = microsoft.execute(
                organization_id,
                lambda db: actor(db, request, organization_id),
                "files_write",
                lambda graph, token: save_document(graph, token, item, content, media_type),
            )
            status, error = "completed", None
        except HTTPException as failure:
            result, error = None, failure.detail
            status = "unknown" if error == "sharepoint_save_unknown" else "failed"
        with factory.begin() as db:
            # Finish the original owner's receipt even if access was revoked after
            # dispatch. The response is authorized again below; no data is reassigned.
            receipt = db.get(SharePointSave, save_id)
            receipt.status, receipt.error_code, receipt.result = status, error, result
            receipt.finished_at = now()
        with factory.begin() as db:
            user = actor(db, request, organization_id, licensed=False)
            return save_view(owned(db, SharePointSave, organization_id, user.id, save_id))

    @router.post(PREFIX + "/saves/{save_id}/verify")
    def verify(organization_id: str, save_id: str, request: Request):
        with factory.begin() as db:
            user = actor(db, request, organization_id)
            item = owned(db, SharePointSave, organization_id, user.id, save_id)
            if save_view(item)["status"] != "unknown":
                return save_view(item)
            artifact = owned(db, Artifact, organization_id, user.id, item.artifact_id)
            digest = artifact.sha256
            db.expunge(item)

        def check(graph, token):
            _, existing = inspect_destination(graph, token, item.drive_id, item.folder_id, item.filename)
            if existing is None:
                raise GraphError(409, "sharepoint_save_unknown")
            downloaded = content_download(graph, token, drive_id=item.drive_id, item_id=existing["id"])
            if (
                hashlib.sha256(base64.b64decode(downloaded["content_base64"], validate=True)).hexdigest()
                != digest
            ):
                raise GraphError(409, "sharepoint_save_unknown")
            return {
                "item_id": existing["id"],
                "name": item.filename,
                "size": downloaded["files"][0]["size"],
                "url": downloaded["files"][0]["url"],
                "verified_current_content": True,
            }

        result = microsoft.execute(
            organization_id, lambda db: actor(db, request, organization_id), "files_write", check
        )
        with factory.begin() as db:
            user = actor(db, request, organization_id)
            receipt = owned(db, SharePointSave, organization_id, user.id, save_id)
            if save_view(receipt)["status"] == "unknown":
                receipt.status, receipt.result, receipt.error_code = "completed", result, None
                receipt.finished_at = now()
            return save_view(receipt)

    return router
