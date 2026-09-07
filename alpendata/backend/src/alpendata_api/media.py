"""Private, idempotent specialist calls. Dictation only creates editable text."""

import base64
import hashlib
import json
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field
from sqlalchemy import func, select

from .access import owned
from .auth import authenticate, request_authorization
from .connections import lock_member
from .media_provider import MediaProvider, specialist_key
from .models import Conversation, MediaCall, now
from .schemas import Input


class DictationInput(Input):
    request_id: UUID
    language: Literal["fr", "en"]
    media_type: Literal["audio/webm", "audio/mp4", "audio/wav", "audio/mpeg"]
    content_base64: str = Field(min_length=1, max_length=2796204)


class VisionInput(Input):
    file_id: UUID
    version: int = Field(ge=1)
    question: str = Field(min_length=1, max_length=2000)


def media_view(row):
    status = "interrupted" if row.status == "running" and row.created_at + 120 < now() else row.status
    return {
        "id": row.id,
        "kind": row.kind,
        "model": row.model,
        "provider": "Mistral",
        "status": status,
        "text": row.text if status == "completed" else "",
    }


def complete(
    settings,
    factory,
    authorize,
    conversation_id,
    identifier,
    kind,
    content,
    media_type,
    prompt="",
    language="fr",
    turn_id=None,
    provider=None,
):
    digest = hashlib.sha256(content + json.dumps([kind, media_type, prompt, language]).encode()).hexdigest()
    with factory.begin() as db:
        user = authorize(db)
        conversation = owned(db, Conversation, user[0], user[1], conversation_id)
        model = (
            (conversation.service_features or {}).get("vision")
            if kind == "vision"
            else settings.transcription_model
        )
        if not model or not specialist_key(settings) or (kind == "vision" and model != settings.vision_model):
            raise HTTPException(503, "media_not_configured")
        existing = db.get(MediaCall, identifier)
        if existing:
            if (
                existing.organization_id,
                existing.owner_id,
                existing.conversation_id,
                existing.input_hash,
            ) != (*user, conversation_id, digest):
                raise HTTPException(409, "media_request_conflict")
            return media_view(existing)
        count = db.scalar(
            select(func.count())
            .select_from(MediaCall)
            .where(
                MediaCall.organization_id == user[0],
                MediaCall.owner_id == user[1],
                MediaCall.created_at > now() - 3600,
            )
        )
        if count >= 60:
            raise HTTPException(429, "media_rate_limited")
        row = MediaCall(
            id=identifier,
            organization_id=user[0],
            owner_id=user[1],
            conversation_id=conversation_id,
            turn_id=turn_id,
            kind=kind,
            input_hash=digest,
            model=model,
        )
        db.add(row)
    try:
        result = (provider or MediaProvider(settings)).complete(
            kind, model, content, media_type, prompt, language
        )
    except HTTPException:
        with factory.begin() as db:
            db.get(MediaCall, identifier).status = "failed"
        raise
    with factory.begin() as db:
        authorize(db)
        row = db.get(MediaCall, identifier)
        row.text, row.status = result["text"], "completed"
        # A provider may identify a dated model behind an alias. Keep its attribution.
        if isinstance(result.get("model"), str) and len(result["model"]) <= 200:
            row.model = result["model"]
        return media_view(row)


def read_image(settings, factory, job, payload, authorize_job, provider=None):
    from .workspace_file_tool import access_file

    body = VisionInput.model_validate(payload)
    with factory.begin() as db:
        authorize_job(db, job)
        from .models import ChatTurn

        turn = db.get(ChatTurn, job.id)
        conversation_id = turn.conversation_id
        result = access_file(
            db, settings, turn, {"operation": "read", "file_id": str(body.file_id), "version": body.version}
        )
        filename = result["files"][0]["name"]
        extension = filename.rsplit(".", 1)[-1].lower()
        if extension not in {"png", "jpg", "jpeg"}:
            raise HTTPException(422, "vision_image_required")
        content = base64.b64decode(result["content_base64"])

    def authorize(db):
        authorize_job(db, job)
        # Re-check project access if a publication was revoked during image reading.
        from .file_access import file_access

        file_access(db, job.organization_id, job.owner_id, str(body.file_id))
        return job.organization_id, job.owner_id

    identifier = str(uuid5(NAMESPACE_URL, job.id + json.dumps(body.model_dump(mode="json"), sort_keys=True)))
    result = complete(
        settings,
        factory,
        authorize,
        conversation_id,
        identifier,
        "vision",
        content,
        "image/png" if extension == "png" else "image/jpeg",
        body.question,
        turn_id=job.id,
        provider=provider,
    )
    return {**result, "filename": filename, "version": body.version}


def media_router(settings, factory):
    router = APIRouter()
    path = "/api/organizations/{organization_id}/chat/conversations/{conversation_id}/dictations"

    def actor(db, request, organization_id):
        user = authenticate(db, request_authorization(request, settings))
        lock_member(db, user, organization_id)
        return organization_id, user.id

    @router.post(path)
    def dictate(organization_id: str, conversation_id: str, request: Request, body: DictationInput):
        try:
            data = base64.b64decode(body.content_base64, validate=True)
        except ValueError:
            raise HTTPException(422, "dictation_format_invalid") from None
        valid = {
            "audio/webm": data.startswith(b"\x1aE\xdf\xa3"),
            "audio/mp4": data[4:8] == b"ftyp",
            "audio/wav": data.startswith(b"RIFF") and data[8:12] == b"WAVE",
            "audio/mpeg": data.startswith(b"ID3") or data[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"),
        }
        if not data or len(data) > 2 * 1024 * 1024 or not valid[body.media_type]:
            raise HTTPException(422, "dictation_format_invalid")
        return complete(
            settings,
            factory,
            lambda db: actor(db, request, organization_id),
            conversation_id,
            str(body.request_id),
            "dictation",
            data,
            body.media_type,
            language=body.language,
        )

    @router.get(path + "/{request_id}")
    def result(organization_id: str, conversation_id: str, request_id: str, request: Request):
        with factory.begin() as db:
            _, user_id = actor(db, request, organization_id)
            row = owned(db, MediaCall, organization_id, user_id, request_id)
            if row.conversation_id != conversation_id or row.kind != "dictation":
                raise HTTPException(404, "resource_not_found")
            return media_view(row)

    return router
