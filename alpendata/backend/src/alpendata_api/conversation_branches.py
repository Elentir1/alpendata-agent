"""Branches copy visible history, never tool calls or action authorizations."""

from typing import Literal
from uuid import UUID, uuid4

from fastapi import HTTPException, Request
from fastapi.responses import Response
from pydantic import Field
from sqlalchemy import func, select

from .access import owned
from .file_access import unpublished_file
from .models import ChatTurn, Conversation, FileVersion, WorkspaceFile, now
from .schemas import Input
from .work_settings import WorkSettings


class BranchInput(Input):
    request_id: UUID
    through_sequence: int = Field(ge=0)
    work_settings: WorkSettings | None = None
    integration_provider: Literal["microsoft", "infomaniak"] | None = None


def branch_history(db, conversation):
    if not conversation.parent_id:
        return []
    rows = db.scalars(
        select(ChatTurn)
        .where(
            ChatTurn.conversation_id == conversation.id,
            ChatTurn.sequence <= conversation.branch_sequence,
            ChatTurn.status == "completed",
        )
        .order_by(ChatTurn.sequence)
    ).all()
    return [
        message
        for row in rows
        for message in (
            {"role": "user", "content": row.message},
            {"role": "assistant", "content": row.response or ""},
        )
    ]


def attach_branch_routes(router, settings, factory, actor):
    from .chat import PREFIX, conversation_view, create_conversation

    @router.post(PREFIX + "/conversations/{conversation_id}/branches", status_code=201)
    def branch(organization_id: str, conversation_id: str, request: Request, body: BranchInput):
        with factory.begin() as db:
            user = actor(db, request, organization_id)
            source = owned(db, Conversation, organization_id, user.id, conversation_id)
            work_settings = body.work_settings.model_dump() if body.work_settings else source.work_settings
            provider = body.integration_provider or source.integration_provider
            existing = db.get(Conversation, str(body.request_id))
            if existing:
                if (
                    existing.organization_id,
                    existing.owner_id,
                    existing.parent_id,
                    existing.branch_sequence,
                    existing.integration_provider,
                    existing.work_settings,
                ) != (organization_id, user.id, source.id, body.through_sequence, provider, work_settings):
                    raise HTTPException(409, "chat_request_conflict")
                return conversation_view(existing)
            rows = db.scalars(
                select(ChatTurn)
                .where(
                    ChatTurn.conversation_id == source.id,
                    ChatTurn.sequence <= body.through_sequence,
                )
                .order_by(ChatTurn.sequence)
            ).all()
            if body.through_sequence and (not rows or rows[-1].sequence != body.through_sequence):
                raise HTTPException(422, "chat_branch_sequence_invalid")
            if any(row.status in ("queued", "running") for row in rows):
                raise HTTPException(409, "chat_branch_running")
            if sum(len(row.message) + len(row.response or "") for row in rows) > 500000:
                raise HTTPException(409, "chat_branch_context_too_large")
            files = db.execute(
                select(WorkspaceFile, FileVersion)
                .join(FileVersion, FileVersion.file_id == WorkspaceFile.id)
                .where(
                    WorkspaceFile.conversation_id == source.id,
                    unpublished_file(),
                    FileVersion.version == WorkspaceFile.version,
                )
            ).all()
            used = db.scalar(
                select(func.coalesce(func.sum(FileVersion.size), 0)).where(
                    FileVersion.organization_id == organization_id, FileVersion.owner_id == user.id
                )
            )
            if used + sum(version.size for _, version in files) > 500 * 1024 * 1024:
                raise HTTPException(413, "document_storage_quota")
            target = create_conversation(
                db,
                settings,
                user,
                organization_id,
                source.language,
                source.title[:145] + (" · Variante" if source.language == "fr" else " · Branch"),
                project_id=source.context_project_id,
                integration_provider=provider,
                work_settings=work_settings,
                extra_prompt="\nThis conversation continues a copied transcript. "
                "Past action claims are historical, "
                "not new tool results. Never repeat a past action unless the user explicitly asks. "
                "Attachments were copied at their current version when this branch was created. "
                "List this conversation's files to find their new IDs; "
                "old transcript file IDs are historical.\n",
            )
            # This UUID also makes uncertain branch creation safe to retry.
            target.id = str(body.request_id)
            target.project_id = source.project_id
            target.parent_id, target.branch_sequence = source.id, body.through_sequence
            db.flush()
            for file, version in files:
                copied = WorkspaceFile(
                    organization_id=organization_id,
                    owner_id=user.id,
                    conversation_id=target.id,
                    filename=file.filename,
                    media_type=file.media_type,
                    version=1,
                )
                db.add(copied)
                db.flush()
                db.add(
                    FileVersion(
                        organization_id=organization_id,
                        owner_id=user.id,
                        file_id=copied.id,
                        version=1,
                        object_key=version.object_key,
                        sha256=version.sha256,
                        size=version.size,
                        analysis_status="queued"
                        if version.analysis_status in ("queued", "running")
                        else version.analysis_status,
                        analysis_text=version.analysis_text,
                        analysis_pages=version.analysis_pages,
                    )
                )
            for row in rows:
                db.add(
                    ChatTurn(
                        organization_id=organization_id,
                        owner_id=user.id,
                        conversation_id=target.id,
                        request_id=str(uuid4()),
                        sequence=row.sequence,
                        message=row.message,
                        response=row.response,
                        status=row.status,
                        error_code=row.error_code,
                        created_at=row.created_at,
                        finished_at=row.finished_at or now(),
                    )
                )
            db.flush()
            return conversation_view(target)

    @router.get(PREFIX + "/conversations/{conversation_id}/export")
    def export(organization_id: str, conversation_id: str, request: Request):
        with factory.begin() as db:
            user = actor(db, request, organization_id, licensed=False)
            item = owned(db, Conversation, organization_id, user.id, conversation_id)
            turns = db.scalars(
                select(ChatTurn).where(ChatTurn.conversation_id == item.id).order_by(ChatTurn.sequence)
            ).all()
            text = f"# {item.title}\n\n"
            for turn in turns:
                text += f"## {'Vous' if item.language == 'fr' else 'You'}\n\n{turn.message}\n\n"
                text += f"## AlpenData\n\n{turn.response or '[' + turn.status + ']'}\n\n"
            return Response(
                text,
                media_type="text/markdown; charset=utf-8",
                headers={
                    "Content-Disposition": 'attachment; filename="alpendata-conversation.md"',
                    "Cache-Control": "no-store",
                },
            )
