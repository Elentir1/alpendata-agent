"""Collabora WOPI sessions: private snapshots, persistent locks and immutable saves."""

from typing import Literal

import jwt
from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from .access import member
from .artifacts import validate_document
from .auth import authenticate, request_authorization
from .connections import lock_member
from .file_access import file_access
from .file_store import LIMIT
from .models import EditorSession, User, now
from .office_discovery import editor_action
from .office_versions import save_snapshot, snapshot
from .schemas import Input
from .workspace_files import file_store, version_record


class EditorInput(Input):
    language: Literal["fr", "en"] = "fr"
    mobile: bool = False


def office_router(settings, factory):
    router = APIRouter()
    root = "/api/organizations/{organization_id}/files/{file_id}/editor"
    wopi = "/api/editor/wopi/files/{session_id}"

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
            if session.expires_at <= now():
                raise HTTPException(403, "document_editor_session_expired")
        else:
            member(db, user, session.organization_id, licensed=False)
        # Revalidate write access on reads too: an editor downgraded to reader must close.
        item = file_access(db, session.organization_id, user.id, session.file_id, write=True)
        return session, item, user

    def authorize(request, session_id):
        enabled()
        token = request.query_params.get("access_token", "")
        try:
            claims = jwt.decode(
                token,
                settings.office_secret,
                algorithms=["HS256"],
                audience="collabora-wopi",
                options={"require": ["sid", "exp", "aud"]},
            )
            if claims["sid"] != session_id:
                raise ValueError("Session mismatch")
        except (jwt.PyJWTError, ValueError):
            raise HTTPException(401, "document_editor_token_invalid") from None

    @router.post(root, status_code=201)
    def create(organization_id: str, file_id: str, request: Request, body: EditorInput):
        enabled()
        with factory.begin() as db:
            user = authenticate(db, request_authorization(request, settings))
            lock_member(db, user, organization_id)
            item = file_access(db, organization_id, user.id, file_id, write=True)
            extension = item.filename.rsplit(".", 1)[-1].lower()
            if extension not in {"docx", "xlsx", "pptx"}:
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
            source = settings.public_origin + wopi.replace("{session_id}", session.id)
            action = editor_action(settings.office_origin, extension, body.language, source)
            token = jwt.encode(
                {"sid": session.id, "aud": "collabora-wopi", "exp": session.expires_at},
                settings.office_secret,
                algorithm="HS256",
            )
            return {
                "id": session.id,
                "base_version": session.base_version,
                "provider": "collabora",
                "action_url": action,
                "access_token": token,
                "access_token_ttl": session.expires_at * 1000,
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

    @router.get(wopi)
    def info(session_id: str, request: Request):
        authorize(request, session_id)
        with factory.begin() as db:
            session, original, user = session_access(db, session_id)
            item, number = snapshot(db, session, original)
            version = version_record(db, item, number)
            return {
                "BaseFileName": item.filename,
                "OwnerId": item.owner_id,
                "Size": version.size,
                "Version": f"{item.id}:{number}",
                "UserId": user.id,
                "UserFriendlyName": user.display_name,
                "UserCanWrite": True,
                "UserCanNotWriteRelative": True,
                "SupportsUpdate": True,
                "SupportsLocks": True,
                "SupportsGetLock": True,
                "SupportsRename": False,
                "PostMessageOrigin": settings.public_origin,
                "EnableOwnerTermination": False,
            }

    @router.get(wopi + "/contents")
    def content(session_id: str, request: Request):
        authorize(request, session_id)
        with factory.begin() as db:
            session, original, _ = session_access(db, session_id)
            item, number = snapshot(db, session, original)
            data = file_store(settings).get(version_record(db, item, number).object_key)
            return Response(
                data, media_type=item.media_type, headers={"X-WOPI-ItemVersion": f"{item.id}:{number}"}
            )

    def current_lock(session):
        return session.lock_value if (session.lock_expires_at or 0) > now() else ""

    def mismatch(value):
        return Response(status_code=409, headers={"X-WOPI-Lock": value or ""})

    @router.post(wopi)
    def lock(session_id: str, request: Request):
        authorize(request, session_id)
        operation = request.headers.get("X-WOPI-Override")
        if operation not in {"LOCK", "REFRESH_LOCK", "UNLOCK", "GET_LOCK"}:
            raise HTTPException(501, "document_editor_operation_unsupported")
        value, previous = request.headers.get("X-WOPI-Lock", ""), request.headers.get("X-WOPI-OldLock")
        if operation != "GET_LOCK" and (
            not value or len(value.encode()) > 1024 or any(ord(c) < 32 or ord(c) > 126 for c in value)
        ):
            raise HTTPException(400, "document_editor_lock_invalid")
        with factory.begin() as db:
            session, _, _ = session_access(db, session_id, write=True)
            current = current_lock(session)
            if operation == "GET_LOCK":
                return Response(headers={"X-WOPI-Lock": current or ""})
            if previous is not None:
                if operation != "LOCK" or not current or previous != current:
                    return mismatch(current)
            elif (current and current != value) or (not current and operation != "LOCK"):
                return mismatch(current)
            session.lock_value = None if operation == "UNLOCK" else value
            session.lock_expires_at = None if operation == "UNLOCK" else now() + 1800
            return Response()

    def put(session_id, lock_value, data):
        with factory.begin() as db:
            session, original, _ = session_access(db, session_id, write=True)
            current = current_lock(session)
            if not current or current != lock_value:
                return mismatch(current)
            validate_document(original.filename, data)
            item, number = save_snapshot(db, settings, session, original, data)
            return Response(headers={"X-WOPI-ItemVersion": f"{item.id}:{number}"})

    @router.post(wopi + "/contents")
    async def put_file(session_id: str, request: Request):
        authorize(request, session_id)
        if request.headers.get("X-WOPI-Override") != "PUT":
            raise HTTPException(501, "document_editor_operation_unsupported")
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > LIMIT:
                raise HTTPException(413, "document_too_large")
        return await run_in_threadpool(put, session_id, request.headers.get("X-WOPI-Lock", ""), bytes(data))

    return router
