"""Parsing is retryable: it has no model, integrations or external side effects."""

import base64
from dataclasses import replace
from uuid import uuid4

from sqlalchemy import or_, select

from .access import member
from .file_access import publication
from .models import Conversation, FileVersion, Project, User, WorkspaceFile, now
from .runtime import ContainerRuntime, RuntimeFailure
from .workspace_files import file_store


class DocumentWorker:
    def __init__(self, settings, factory):
        self.settings, self.factory = settings, factory

    def run_once(self):
        with self.factory.begin() as db:
            row = db.scalar(
                select(FileVersion)
                .where(
                    or_(
                        FileVersion.analysis_status == "queued",
                        (FileVersion.analysis_status == "running")
                        & (FileVersion.analysis_expires_at < now()),
                    )
                )
                .order_by(FileVersion.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if row is None:
                return False
            published = publication(db, row.file_id)
            analysis_owner = db.get(Project, published.project_id).owner_id if published else row.owner_id
            user = db.get(User, analysis_owner)
            try:
                if user is None or not user.active:
                    raise RuntimeFailure("document_analysis_access_revoked")
                member(db, user, row.organization_id, licensed=False)
            except Exception:
                row.analysis_status = "access_revoked"
                return True
            item = db.get(WorkspaceFile, row.file_id)
            if not published and db.get(Conversation, item.conversation_id).deleted_at is not None:
                row.analysis_status = "access_revoked"
                return True
            row.analysis_status, row.analysis_lease, row.analysis_expires_at = (
                "running",
                str(uuid4()),
                now() + 120,
            )
            identifier, org, owner, key, lease, name = (
                row.id,
                row.organization_id,
                analysis_owner,
                row.object_key,
                row.analysis_lease,
                item.filename,
            )

        def check():
            with self.factory() as db:
                user = db.get(User, owner)
                if user is None or not user.active:
                    raise RuntimeFailure("document_analysis_access_revoked")
                member(db, user, org, licensed=False)
                current = db.get(FileVersion, identifier)
                if current is None or current.analysis_lease != lease or current.analysis_expires_at < now():
                    raise RuntimeFailure("document_analysis_lease_lost")
                item = db.get(WorkspaceFile, current.file_id)
                if (
                    not publication(db, item.id)
                    and db.get(Conversation, item.conversation_id).deleted_at is not None
                ):
                    raise RuntimeFailure("document_analysis_access_revoked")

        try:
            runtime = ContainerRuntime(
                replace(
                    self.settings.runtime,
                    state_root=self.settings.runtime.state_root.parent / "document-analysis",
                    timeout_seconds=60,
                )
            )
            payload = {
                "operation": "analyze_document",
                "state_scope": identifier,
                "filename": name,
                "content_base64": base64.b64encode(file_store(self.settings).get(key)).decode(),
            }

            def reject(*_):
                raise RuntimeFailure("document_analysis_tools_forbidden")

            result = runtime.run(org, owner, payload, reject, check=check)
            if result.get("status") not in ("ready", "no_text", "vision_required", "password_required"):
                raise ValueError("Invalid analysis")
            pages = result.get("pages", [])
            if (
                not isinstance(pages, list)
                or len(pages) > 500
                or sum(len(item["text"]) for item in pages) > 300000
            ):
                raise ValueError("Invalid analysis")
            for page in pages:
                if (
                    not isinstance(page.get("reference"), str)
                    or len(page["reference"]) > 512
                    or not isinstance(page.get("text"), str)
                ):
                    raise ValueError("Invalid analysis")
            check()
        except Exception:
            result, pages = {"status": "failed"}, []
        with self.factory.begin() as db:
            row = db.scalar(select(FileVersion).where(FileVersion.id == identifier).with_for_update())
            if row and row.analysis_lease == lease:
                row.analysis_status = "partial" if result.get("partial") else result["status"]
                row.analysis_pages = pages
                row.analysis_text = "\n".join(page["text"] for page in pages)
                row.analysis_expires_at = None
        return True
