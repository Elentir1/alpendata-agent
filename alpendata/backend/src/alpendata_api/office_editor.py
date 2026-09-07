"""Signed ONLYOFFICE sessions with immutable saves and conflict preservation."""

import hashlib
from typing import Literal
from urllib.parse import urlsplit

import jwt
import requests
from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import select

from .access import member
from .artifacts import validate_document
from .auth import authenticate, request_authorization
from .connections import lock_member
from .file_access import file_access, publication
from .file_store import LIMIT
from .models import EditorSession, ProjectFile, User, WorkspaceFile, now
from .schemas import Input
from .workspace_files import add_version, file_store, version_record


class EditorInput(Input):
    language: Literal["fr", "en"] = "fr"
    mobile: bool = False


def office_router(settings, factory):
    router = APIRouter()
    root = "/api/organizations/{organization_id}/files/{file_id}/editor"

    def enabled():
        if not settings.office_origin or not settings.office_secret:
            raise HTTPException(503, "document_editor_not_configured")

    def session_access(db, identifier, write=False):
        session = db.get(EditorSession, identifier)
        if not session or session.expires_at <= now():
            raise HTTPException(403, "document_editor_session_expired")
        user = db.get(User, session.editor_id or session.owner_id)
        if not user or not user.active:
            raise HTTPException(403, "document_editor_access_revoked")
        if write:
            lock_member(db, user, session.organization_id)
            session = db.scalar(
                select(EditorSession)
                .where(EditorSession.id == identifier)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        else:
            member(db, user, session.organization_id, licensed=False)
        item = file_access(db, session.organization_id, user.id, session.file_id, write=write)
        return session, item

    @router.post(root, status_code=201)
    def create(organization_id: str, file_id: str, request: Request, body: EditorInput):
        enabled()
        with factory.begin() as db:
            user = authenticate(db, request_authorization(request, settings))
            lock_member(db, user, organization_id)
            item = file_access(db, organization_id, user.id, file_id, write=True)
            extension = item.filename.rsplit(".", 1)[-1].lower()
            types = {"docx": "word", "xlsx": "cell", "pptx": "slide"}
            if extension not in types:
                raise HTTPException(422, "document_editable_copy_required")
            session = EditorSession(
                organization_id=organization_id,
                owner_id=item.owner_id,
                editor_id=user.id,
                file_id=item.id,
                base_version=item.version,
                expires_at=now() + 43200,
            )
            db.add(session)
            db.flush()
            token = jwt.encode(
                {"sid": session.id, "aud": "file-download", "exp": session.expires_at},
                settings.office_secret,
                algorithm="HS256",
            )
            config = {
                "type": "mobile" if body.mobile else "desktop",
                "documentType": types[extension],
                "width": "100%",
                "height": "100%",
                "document": {
                    "fileType": extension,
                    "key": session.id,
                    "title": item.filename,
                    "url": settings.public_origin + "/api/editor/content?token=" + token,
                    "permissions": {"edit": True, "download": True, "print": True},
                },
                "editorConfig": {
                    "mode": "edit",
                    "lang": body.language,
                    "callbackUrl": settings.public_origin + "/api/editor/callback/" + session.id,
                    "user": {"id": user.id, "name": user.display_name},
                    "customization": {"forcesave": True, "autosave": True},
                },
            }
            config["token"] = jwt.encode(config, settings.office_secret, algorithm="HS256")
            return {
                "id": session.id,
                "base_version": session.base_version,
                "automation_enabled": settings.office_automation_enabled,
                "script_url": settings.office_origin + "/web-apps/apps/api/documents/api.js",
                "config": config,
            }

    @router.get(root + "/{session_id}")
    def status(organization_id: str, file_id: str, session_id: str, request: Request):
        with factory() as db:
            user = authenticate(db, request_authorization(request, settings))
            member(db, user, organization_id, licensed=False)
            session = db.get(EditorSession, session_id)
            if (
                not session
                or session.organization_id != organization_id
                or (session.editor_id or session.owner_id) != user.id
                or session.file_id != file_id
            ):
                raise HTTPException(404, "resource_not_found")
            file_access(db, organization_id, user.id, file_id)
            return {"saved_version": session.saved_version, "conflict_file_id": session.conflict_file_id}

    @router.get("/api/editor/content")
    def content(token: str):
        enabled()
        try:
            claims = jwt.decode(
                token,
                settings.office_secret,
                algorithms=["HS256"],
                audience="file-download",
                options={"require": ["exp", "aud", "sid"]},
            )
        except jwt.PyJWTError:
            raise HTTPException(403, "document_editor_token_invalid") from None
        with factory() as db:
            session, item = session_access(db, claims["sid"])
            data = file_store(settings).get(version_record(db, item, session.base_version).object_key)
            return Response(data, media_type=item.media_type)

    @router.post("/api/editor/callback/{session_id}")
    def callback(session_id: str, request: Request, body: dict):
        enabled()
        token = request.headers.get("authorization", "").removeprefix("Bearer ") or body.get("token", "")
        try:
            signed = jwt.decode(
                token, settings.office_secret, algorithms=["HS256"], options={"verify_aud": False}
            )
            payload = signed.get("payload", signed)
            if payload.get("key") != session_id or type(payload.get("status")) is not int:
                raise ValueError
        except (jwt.PyJWTError, ValueError, AttributeError):
            raise HTTPException(403, "document_editor_token_invalid") from None
        with factory.begin() as db:
            session, item = session_access(db, session_id, write=True)
            if payload["status"] not in (2, 6):
                return {"error": 0 if payload["status"] in (1, 4) else 1}
            url = payload.get("url", "")
            parsed = urlsplit(url)
            if (
                parsed.scheme + "://" + parsed.netloc != settings.office_origin
                or parsed.username
                or parsed.password
                or parsed.fragment
            ):
                raise HTTPException(400, "document_editor_url_invalid")
            try:
                with requests.Session() as transport:
                    transport.trust_env = False
                    with transport.get(url, timeout=(5, 20), allow_redirects=False, stream=True) as response:
                        if response.status_code != 200:
                            return {"error": 1}
                        data = bytearray()
                        for chunk in response.iter_content(65536):
                            data.extend(chunk)
                            if len(data) > LIMIT:
                                raise HTTPException(413, "document_too_large")
            except requests.RequestException:
                return {"error": 1}
            data = bytes(data)
            validate_document(item.filename, data)
            current = version_record(db, item, item.version)
            if current.sha256 == hashlib.sha256(data).hexdigest():
                session.saved_version = item.version
                return {"error": 0}
            expected = session.saved_version or session.base_version
            if item.version != expected or session.conflict_file_id:
                conflict = (
                    file_access(
                        db,
                        item.organization_id,
                        session.editor_id or session.owner_id,
                        session.conflict_file_id,
                        write=True,
                    )
                    if session.conflict_file_id
                    else None
                )
                if not conflict:
                    stem, extension = item.filename.rsplit(".", 1)
                    conflict = WorkspaceFile(
                        organization_id=item.organization_id,
                        owner_id=item.owner_id,
                        conversation_id=item.conversation_id,
                        filename=stem[:145] + " (copie)." + extension,
                        media_type=item.media_type,
                    )
                    db.add(conflict)
                    db.flush()
                    add_version(db, file_store(settings), conflict, data)
                    shared = publication(db, item.id)
                    if shared:
                        db.add(
                            ProjectFile(
                                organization_id=item.organization_id,
                                owner_id=item.owner_id,
                                project_id=shared.project_id,
                                file_id=conflict.id,
                                source_file_id=item.id,
                                source_version=expected,
                            )
                        )
                    session.conflict_file_id = conflict.id
                elif (
                    version_record(db, conflict, conflict.version).sha256 != hashlib.sha256(data).hexdigest()
                ):
                    add_version(db, file_store(settings), conflict, data, conflict.version)
            else:
                add_version(db, file_store(settings), item, data, expected)
                session.saved_version = item.version
            return {"error": 0}

    return router
