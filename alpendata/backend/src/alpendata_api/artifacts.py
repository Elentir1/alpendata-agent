"""Immutable private downloads received as bytes from an authorized runtime job."""

import base64
import binascii
import hashlib
import io
import unicodedata
import zipfile
import zlib
from pathlib import PurePosixPath
from urllib.parse import quote
from xml.etree import ElementTree

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import Field
from sqlalchemy import func, select

from .access import member, owned
from .auth import authenticate, request_authorization
from .models import Artifact
from .schemas import Input

MAX_BYTES = 5 * 1024 * 1024
OWNER_BYTES = 100 * 1024 * 1024
OFFICE = {
    ".docx": ("word/document.xml", "wordprocessingml.document"),
    ".xlsx": ("xl/workbook.xml", "spreadsheetml.sheet"),
    ".pptx": ("ppt/presentation.xml", "presentationml.presentation"),
}


class ArtifactInput(Input):
    filename: str = Field(min_length=1, max_length=180)
    content_base64: str = Field(min_length=1, max_length=4 * ((MAX_BYTES + 2) // 3))


def validate_document(filename, content):
    """Check the format/container, not visual correctness or malware absence."""
    if (
        filename != filename.strip()
        or any(character in filename for character in '/\\:<>"|?*')
        or any(unicodedata.category(character).startswith("C") for character in filename)
        or filename.startswith(".")
    ):
        raise HTTPException(400, "document_filename_invalid")
    extension = PurePosixPath(filename).suffix.lower()
    if not content or len(content) > MAX_BYTES:
        raise HTTPException(413, "document_too_large")
    if extension == ".pdf":
        if not content.startswith(b"%PDF-") or b"%%EOF" not in content[-1024:]:
            raise HTTPException(400, "document_format_invalid")
        return "application/pdf"
    if extension not in OFFICE:
        raise HTTPException(400, "document_format_unsupported")
    main, kind = OFFICE[extension]
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as package:
            entries = package.infolist()
            names = [entry.filename for entry in entries]
            if (
                len(entries) > 2048
                or len(names) != len(set(names))
                or sum(entry.file_size for entry in entries) > 50 * 1024 * 1024
                or any(entry.flag_bits & 1 for entry in entries)
                or any(
                    ".." in PurePosixPath(name).parts or name.startswith("/") or "\\" in name
                    for name in names
                )
                or main not in names
                or package.getinfo("[Content_Types].xml").file_size > 1024 * 1024
            ):
                raise ValueError("Invalid package")
            xml = package.read("[Content_Types].xml")
            if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
                raise ValueError("Invalid XML")
            declarations = ElementTree.fromstring(xml)
            expected = f"application/vnd.openxmlformats-officedocument.{kind}.main+xml"
            if not any(
                item.get("PartName") == "/" + main and item.get("ContentType") == expected
                for item in declarations
            ):
                raise ValueError("Wrong Office format")
            if package.testzip() is not None:
                raise ValueError("Damaged package")
    except (
        KeyError,
        ValueError,
        zipfile.BadZipFile,
        zlib.error,
        RuntimeError,
        NotImplementedError,
        ElementTree.ParseError,
    ):
        raise HTTPException(400, "document_format_invalid") from None
    return f"application/vnd.openxmlformats-officedocument.{kind}"


def artifact_view(item):
    return {
        key: getattr(item, key) for key in ("id", "filename", "media_type", "size", "sha256", "created_at")
    }


def turn_artifacts(db, turn):
    return [
        artifact_view(item)
        for item in db.scalars(
            select(Artifact)
            .where(
                Artifact.organization_id == turn.organization_id,
                Artifact.owner_id == turn.owner_id,
                Artifact.turn_id == turn.id,
            )
            .order_by(Artifact.created_at, Artifact.id)
        )
    ]


def publish_document(db, turn, payload):
    """The caller holds the membership and live turn lease locks throughout."""
    request = ArtifactInput.model_validate(payload)
    try:
        content = base64.b64decode(request.content_base64, validate=True)
    except (ValueError, binascii.Error):
        raise HTTPException(400, "document_format_invalid") from None
    media_type = validate_document(request.filename, content)
    digest = hashlib.sha256(content).hexdigest()
    previous = db.scalar(
        select(Artifact).where(
            Artifact.turn_id == turn.id,
            Artifact.filename == request.filename,
            Artifact.sha256 == digest,
            Artifact.organization_id == turn.organization_id,
            Artifact.owner_id == turn.owner_id,
        )
    )
    if previous:
        return artifact_view(previous)
    used = db.scalar(
        select(func.coalesce(func.sum(Artifact.size), 0)).where(
            Artifact.organization_id == turn.organization_id,
            Artifact.owner_id == turn.owner_id,
        )
    )
    count = db.scalar(select(func.count()).select_from(Artifact).where(Artifact.turn_id == turn.id))
    if used + len(content) > OWNER_BYTES or count >= 20:
        raise HTTPException(409, "document_storage_full")
    item = Artifact(
        organization_id=turn.organization_id,
        owner_id=turn.owner_id,
        turn_id=turn.id,
        filename=request.filename,
        media_type=media_type,
        size=len(content),
        sha256=digest,
        content=content,
    )
    db.add(item)
    db.flush()
    return artifact_view(item)


def artifacts_router(settings, factory):
    router = APIRouter()

    @router.get("/api/organizations/{organization_id}/documents/{document_id}/download")
    def download(organization_id: str, document_id: str, request: Request):
        with factory.begin() as db:
            user = authenticate(db, request_authorization(request, settings))
            member(db, user, organization_id, licensed=False)
            item = owned(db, Artifact, organization_id, user.id, document_id)
            return Response(
                content=item.content,
                media_type=item.media_type,
                headers={
                    "Content-Disposition": "attachment; filename*=UTF-8''" + quote(item.filename, safe=""),
                    "Content-Security-Policy": "sandbox; default-src 'none'",
                },
            )

    return router
