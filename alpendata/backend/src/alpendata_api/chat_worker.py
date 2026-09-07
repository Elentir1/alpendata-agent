"""Durable chat worker. PostgreSQL owns jobs; each Hermes state stays private."""

import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, replace
from typing import Literal
from uuid import UUID, uuid4

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import select, update

from .artifacts import publish_document
from .billing_state import billing_access
from .connections import MicrosoftReader, SearchInput, lock_member
from .graph_documents import FileInput
from .model_gateway import ModelError, ModelGateway
from .models import (
    ChatTurn,
    Conversation,
    Membership,
    ModelCall,
    RoutineProposal,
    RoutineTrial,
    ToolRead,
    User,
    now,
)
from .routine_delivery import delivery_accepted
from .routine_service import read_evidence, record_proposals, source_references
from .run_events import record_event
from .runtime import ContainerRuntime, RuntimeFailure
from .schedule_state import finish_occurrence, occurrence_for_turn, scheduled_turn_error
from .work_settings import source_allowed

# A credential refresh followed by a Graph read holds the authorization locks.
# Its bounded network work must fit before the next heartbeat can acquire them.
LEASE_SECONDS = 120


@dataclass(frozen=True)
class Job:
    id: str
    organization_id: str
    owner_id: str
    lease_id: str


class ToolRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    capability: Literal["mail", "calendar", "files"]
    operation: Literal["read", "download"] = "read"
    arguments: dict


def lock_owner(db, organization_id, owner_id):
    return db.scalar(
        select(Membership)
        .where(Membership.organization_id == organization_id, Membership.user_id == owner_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def locked_turn(db, job):
    return db.scalar(
        select(ChatTurn)
        .where(
            ChatTurn.id == job.id,
            ChatTurn.organization_id == job.organization_id,
            ChatTurn.owner_id == job.owner_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def authorize_job(db, job):
    user = db.get(User, job.owner_id)
    if user is None or not user.active:
        raise RuntimeFailure("agent_access_revoked")
    try:
        lock_member(db, user, job.organization_id)
    except HTTPException:
        raise RuntimeFailure("agent_access_revoked") from None
    turn = locked_turn(db, job)
    if (
        turn is None
        or turn.status != "running"
        or turn.lease_id != job.lease_id
        or turn.lease_expires_at <= now()
    ):
        raise RuntimeFailure("agent_lease_lost")
    if turn.cancel_requested:
        raise RuntimeFailure("agent_cancelled")
    if db.get(Conversation, turn.conversation_id).deleted_at is not None:
        raise RuntimeFailure("agent_cancelled")
    from .project_access import conversation_context_access

    try:
        conversation_context_access(db, db.get(Conversation, turn.conversation_id))
    except HTTPException:
        raise RuntimeFailure("project_context_revoked") from None
    scheduled_error = scheduled_turn_error(db, turn)
    if scheduled_error:
        raise RuntimeFailure(scheduled_error)
    return user


def interrupt_expired_turn(db, turn):
    """Caller holds the owner and turn locks and has checked lease expiry."""
    turn.status, turn.error_code, turn.finished_at = (
        "interrupted",
        "agent_worker_interrupted",
        now(),
    )
    turn.lease_expires_at = None
    record_event(db, turn, "interrupted")
    finish_occurrence(db, turn, "agent_worker_interrupted")
    db.execute(
        update(ModelCall)
        .where(ModelCall.turn_id == turn.id, ModelCall.status == "started")
        .values(status="failed", error_code="model_result_unknown", finished_at=now())
    )
    db.execute(
        update(ToolRead)
        .where(ToolRead.turn_id == turn.id, ToolRead.status == "started")
        .values(status="failed", error_code="tool_result_unknown", finished_at=now())
    )


class ChatWorker:
    def __init__(self, settings, factory, *, gateway=None, runtime=None, microsoft=None):
        if not settings.chat_enabled:
            raise ValueError("Chat is not configured")
        self.settings, self.factory = settings, factory
        self.gateway = gateway or ModelGateway(settings.model)
        self.runtime = runtime or ContainerRuntime(settings.runtime)
        self.microsoft = microsoft or MicrosoftReader(settings, factory)

    def recover_expired(self):
        with self.factory.begin() as db:
            expired = db.scalars(
                select(ChatTurn).where(ChatTurn.status == "running", ChatTurn.lease_expires_at <= now())
            ).all()
        for previous in expired:
            with self.factory.begin() as db:
                lock_owner(db, previous.organization_id, previous.owner_id)
                turn = locked_turn(db, Job(previous.id, previous.organization_id, previous.owner_id, ""))
                if turn.status != "running" or turn.lease_expires_at > now():
                    continue
                interrupt_expired_turn(db, turn)
        # No automatic replay: an interrupted tool may already have taken effect.

    def claim(self):
        with self.factory.begin() as db:
            candidates = db.scalars(
                select(ChatTurn)
                .where(ChatTurn.status == "queued")
                .order_by(ChatTurn.created_at, ChatTurn.id)
                .limit(100)
            ).all()
            for candidate in candidates:
                membership = db.scalar(
                    select(Membership)
                    .where(
                        Membership.organization_id == candidate.organization_id,
                        Membership.user_id == candidate.owner_id,
                    )
                    .with_for_update(skip_locked=True)
                )
                if membership is None:
                    continue
                turn = db.scalar(
                    select(ChatTurn)
                    .where(ChatTurn.id == candidate.id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
                if turn.status != "queued":
                    continue
                running = db.execute(
                    select(ChatTurn.conversation_id, Conversation.tool_revision)
                    .join(Conversation, Conversation.id == ChatTurn.conversation_id)
                    .where(
                        ChatTurn.organization_id == turn.organization_id,
                        ChatTurn.owner_id == turn.owner_id,
                        ChatTurn.status == "running",
                    )
                ).all()
                conversation = db.get(Conversation, turn.conversation_id)
                if (
                    len(running) >= 3
                    or any(row.conversation_id == conversation.id for row in running)
                    or (conversation.tool_revision < 7 and any(row.tool_revision < 7 for row in running))
                ):
                    continue
                turn.status, turn.lease_id = "running", str(uuid4())
                turn.started_at, turn.lease_expires_at = now(), now() + LEASE_SECONDS
                record_event(db, turn, "running")
                return Job(turn.id, turn.organization_id, turn.owner_id, turn.lease_id)
            return None

    @contextmanager
    def heartbeat(self, job):
        stopping, interrupted = threading.Event(), threading.Event()
        reason = ["agent_lease_lost"]
        valid_until = [time.monotonic() + LEASE_SECONDS]

        def pulse():
            while not stopping.wait(3):
                try:
                    with self.factory.begin() as db:
                        turn = locked_turn(db, job)
                        if (
                            turn is None
                            or turn.status != "running"
                            or turn.lease_id != job.lease_id
                            or turn.lease_expires_at <= now()
                        ):
                            interrupted.set()
                            return
                        turn.lease_expires_at = now() + LEASE_SECONDS
                        membership = db.get(Membership, (job.organization_id, job.owner_id))
                        user = db.get(User, job.owner_id)
                        if (
                            not user.active
                            or not membership.active
                            or not membership.licensed
                            or not billing_access(db, job.organization_id)
                        ):
                            reason[0] = "agent_access_revoked"
                            interrupted.set()
                        if turn.cancel_requested:
                            reason[0] = "agent_cancelled"
                            interrupted.set()
                        from .project_access import conversation_context_access

                        try:
                            conversation_context_access(db, db.get(Conversation, turn.conversation_id))
                        except HTTPException:
                            reason[0] = "project_context_revoked"
                            interrupted.set()
                    valid_until[0] = time.monotonic() + LEASE_SECONDS
                except Exception:
                    # A lost database connection cannot grant an extended execution.
                    interrupted.set()
                    return

        def check():
            if interrupted.is_set() or time.monotonic() >= valid_until[0]:
                raise RuntimeFailure(reason[0])

        thread = threading.Thread(target=pulse, name="alpendata-job-heartbeat", daemon=True)
        thread.start()
        try:
            yield check
        finally:
            stopping.set()
            thread.join(timeout=10)

    def model(self, job, payload):
        with self.factory.begin() as db:
            authorize_job(db, job)
            call = ModelCall(
                organization_id=job.organization_id,
                owner_id=job.owner_id,
                turn_id=job.id,
                provider=self.settings.model.provider,
                model=self.settings.model.model,
            )
            db.add(call)
            db.flush()
            call_id = call.id
            turn = db.get(ChatTurn, job.id)
            background = bool(payload.get("_alpendata_background"))
            stream = db.get(Conversation, turn.conversation_id).tool_revision >= 7 and not background
            if not background:
                turn.partial_response = None
        last_update = [0.0]

        def on_text(content):
            if time.monotonic() - last_update[0] < 0.5:
                return
            with self.factory.begin() as db:
                authorize_job(db, job)
                turn = db.get(ChatTurn, job.id)
                turn.partial_response = content[:200000]
                record_event(db, turn, "response_updated")
            last_update[0] = time.monotonic()

        try:
            result = (
                self.gateway.complete_stream(payload, on_text)
                if stream and hasattr(self.gateway, "complete_stream")
                else self.gateway.complete(payload)
            )
        except ModelError as error:
            with self.factory.begin() as db:
                call = db.get(ModelCall, call_id)
                call.status, call.error_code, call.finished_at = "failed", error.code, now()
            return {
                "status": error.status,
                "body": {
                    "error": {"message": error.code, "code": error.code, "type": "alpendata_model_error"}
                },
            }
        with self.factory.begin() as db:
            call = db.get(ModelCall, call_id)
            call.status, call.finished_at = "completed", now()
            call.error_code = None
            if result.usage is not None:
                call.prompt_tokens = result.usage.prompt_tokens
                call.completion_tokens = result.usage.completion_tokens
                call.total_tokens = result.usage.total_tokens
        # Keep the receipt even if access changed while the provider was responding.
        with self.factory.begin() as db:
            authorize_job(db, job)
        return result.reply()

    def proposals_tool(self, job, payload):
        if set(payload) != {"proposals"}:
            raise HTTPException(400, "agent_tool_arguments_invalid")
        with self.factory.begin() as db:
            authorize_job(db, job)
            return record_proposals(db, db.get(ChatTurn, job.id), payload)

    def activity(self, job, payload):
        import re

        kind, label = payload.get("kind"), payload.get("label", "")
        if (
            set(payload) != {"kind", "label"}
            or kind not in {"tool_started", "tool_finished"}
            or not isinstance(label, str)
            or not re.fullmatch(r"[A-Za-z0-9_]{1,120}", label)
        ):
            return {"status": 400, "body": {"error": "agent_tool_arguments_invalid"}}
        with self.factory.begin() as db:
            authorize_job(db, job)
            record_event(db, db.get(ChatTurn, job.id), kind, label)
        return {"status": 200, "body": {"recorded": True}}

    def document_tool(self, job, payload):
        with self.factory.begin() as db:
            authorize_job(db, job)
            turn = db.get(ChatTurn, job.id)
            if not db.get(Conversation, turn.conversation_id).documents_enabled:
                raise HTTPException(403, "document_new_conversation_required")
            return publish_document(db, turn, payload)

    def email_draft_tool(self, job, payload):
        from .email_drafts import prepare_email

        with self.factory.begin() as db:
            authorize_job(db, job)
            turn = db.get(ChatTurn, job.id)
            if db.get(Conversation, turn.conversation_id).tool_revision < 3:
                raise HTTPException(403, "email_new_conversation_required")
            return prepare_email(db, turn, payload)

    def email_send_tool(self, job, payload):
        from .agent_email import send_agent_email

        return send_agent_email(self.factory, self.microsoft, authorize_job, job, payload)

    def company_resource_tool(self, job, payload):
        from .company_resource_tool import read_company_resource

        with self.factory.begin() as db:
            authorize_job(db, job)
            return read_company_resource(db, db.get(ChatTurn, job.id), payload)

    def project_context_tool(self, job, payload):
        from .models import ProjectEntry
        from .project_access import project_access

        if set(payload) - {"entry_id"}:
            raise HTTPException(400, "agent_tool_arguments_invalid")
        with self.factory.begin() as db:
            authorize_job(db, job)
            turn = db.get(ChatTurn, job.id)
            conversation = db.get(Conversation, turn.conversation_id)
            if not conversation.context_project_id:
                raise HTTPException(404, "resource_not_found")
            project_access(db, job.organization_id, job.owner_id, conversation.context_project_id)
            query = select(ProjectEntry).where(
                ProjectEntry.project_id == conversation.context_project_id,
                ProjectEntry.organization_id == job.organization_id,
            )
            if payload.get("entry_id"):
                query = query.where(ProjectEntry.id == payload["entry_id"])
            rows = db.scalars(query.order_by(ProjectEntry.created_at.desc()).limit(100)).all()
            return {
                "entries": [
                    {
                        "id": row.id,
                        "title": row.title,
                        "version": row.version,
                        **({"content": row.content} if payload.get("entry_id") else {}),
                    }
                    for row in rows
                ]
            }

    def knowledge_tool(self, job, payload):
        from .knowledge import knowledge_tool

        with self.factory.begin() as db:
            authorize_job(db, job)
            return knowledge_tool(db, db.get(ChatTurn, job.id), payload)

    def workspace_file_tool(self, job, payload):
        from .workspace_file_tool import access_file

        with self.factory.begin() as db:
            authorize_job(db, job)
            return access_file(db, self.settings, db.get(ChatTurn, job.id), payload)

    def vision_tool(self, job, payload):
        from .media import read_image

        return read_image(self.settings, self.factory, job, payload, authorize_job)

    def research_tool(self, job, payload):
        from .research import ResearchInput, read_page, search

        body = ResearchInput.model_validate(payload)
        with self.factory.begin() as db:
            authorize_job(db, job)
            conversation = db.get(Conversation, db.get(ChatTurn, job.id).conversation_id)
            if not (conversation.service_features or {}).get("research"):
                raise HTTPException(403, "research_new_conversation_required")
            receipt = ToolRead(
                organization_id=job.organization_id, owner_id=job.owner_id, turn_id=job.id, capability="web"
            )
            db.add(receipt)
            db.flush()
            identifier = receipt.id

        def check():
            with self.factory.begin() as db:
                authorize_job(db, job)

        try:
            result = (
                search(self.settings, body.query)
                if body.operation == "search"
                else read_page(self.settings, job, body.url, check)
            )
            check()
        except (HTTPException, RuntimeFailure) as error:
            with self.factory.begin() as db:
                receipt = db.get(ToolRead, identifier)
                receipt.status, receipt.error_code, receipt.finished_at = "failed", "research_failed", now()
            if isinstance(error, RuntimeFailure):
                raise HTTPException(502, "research_page_unavailable") from None
            raise
        with self.factory.begin() as db:
            authorize_job(db, job)
            receipt = db.get(ToolRead, identifier)
            receipt.status, receipt.finished_at = "completed", now()
            if body.operation == "read":
                receipt.sources = [{"kind": "web", "label": result["url"], "url": result["url"]}]
            # Search results are discoverable snippets, not proof that pages were read.
        return result

    def calendar_tool(self, job, payload):
        from .calendar_actions import CalendarService, ExecuteInput

        service = CalendarService(self.settings, self.factory, self.microsoft)

        def authorize(db):
            return authorize_job(db, job)

        if payload.get("operation") == "execute":
            try:
                identifier = str(UUID(payload.get("action_id", "")))
            except (ValueError, TypeError, AttributeError):
                raise HTTPException(422, "calendar_arguments_invalid") from None
            body = ExecuteInput.model_validate({"version": payload.get("version")})
            return service.dispatch(
                job.organization_id, authorize, identifier, body.version, automatic_turn=job.id
            )
        if payload.get("operation") != "prepare" or set(payload) != {"operation", "event"}:
            raise HTTPException(422, "calendar_arguments_invalid")
        return service.prepare(job.organization_id, authorize, job.id, payload["event"])

    def tool(self, job, capabilities, payload):
        with self.factory.begin() as db:
            authorize_job(db, job)
            turn = db.get(ChatTurn, job.id)
            conversation = db.get(Conversation, turn.conversation_id)
            required = (
                {
                    "document": "documents",
                    "workspace_file": "documents",
                    "vision": "documents",
                    "project_context": "project",
                    "company_resource": "project",
                    "research": "web",
                }.get(payload.get("kind"))
                if isinstance(payload, dict)
                else None
            )
            if required and not source_allowed(conversation, required):
                return {"status": 403, "body": {"error": "source_not_authorized"}}
        try:
            handlers = {
                "routine_proposals": self.proposals_tool,
                "document": self.document_tool,
                "mail_draft": self.email_draft_tool,
                "mail_send": self.email_send_tool,
                "company_resource": self.company_resource_tool,
                "project_context": self.project_context_tool,
                "workspace_file": self.workspace_file_tool,
                "vision": self.vision_tool,
                "knowledge": self.knowledge_tool,
                "research": self.research_tool,
                "calendar_action": self.calendar_tool,
            }
            if isinstance(payload, dict) and payload.get("kind") in handlers:
                result = handlers[payload["kind"]](
                    job, {key: value for key, value in payload.items() if key != "kind"}
                )
                return {"status": 200, "body": result}
            request = ToolRequest.model_validate(payload)
            if request.capability not in capabilities:
                raise HTTPException(403, "microsoft_permission_required")
            arguments = request.arguments
            if request.operation == "download":
                if request.capability != "files":
                    raise HTTPException(400, "agent_tool_arguments_invalid")
                with self.factory.begin() as db:
                    authorize_job(db, job)
                    turn = db.get(ChatTurn, job.id)
                    conversation = db.get(Conversation, turn.conversation_id)
                    if conversation.tool_revision < 2:
                        raise HTTPException(403, "document_new_conversation_required")
                    provider = conversation.integration_provider
                from .infomaniak_dav import DavFileInput

                validator = DavFileInput if provider == "infomaniak" else FileInput
                arguments = validator.model_validate(arguments).model_dump()
            elif request.capability == "files":
                arguments = SearchInput.model_validate(arguments).model_dump()
            elif request.capability == "mail":
                from .infomaniak import SearchInput as MailSearch

                arguments = MailSearch.model_validate(arguments).model_dump()
            elif arguments:
                raise HTTPException(400, "agent_tool_arguments_invalid")
            with self.factory.begin() as db:
                authorize_job(db, job)
                receipt = ToolRead(
                    organization_id=job.organization_id,
                    owner_id=job.owner_id,
                    turn_id=job.id,
                    capability=request.capability,
                )
                db.add(receipt)
                db.flush()
                receipt_id = receipt.id
            try:
                with self.factory() as db:
                    turn = db.get(ChatTurn, job.id)
                    provider = db.get(Conversation, turn.conversation_id).integration_provider
                reader = self.microsoft
                if provider == "infomaniak":
                    from .infomaniak import InfomaniakReader

                    reader = InfomaniakReader(self.settings, self.factory)
                result = reader.read(
                    job.organization_id,
                    lambda db: authorize_job(db, job),
                    request.capability,
                    operation=request.operation,
                    **arguments,
                )
            except HTTPException as error:
                with self.factory.begin() as db:
                    receipt = db.get(ToolRead, receipt_id)
                    receipt.status, receipt.error_code, receipt.finished_at = (
                        "failed",
                        str(error.detail),
                        now(),
                    )
                raise
            with self.factory.begin() as db:
                receipt = db.get(ToolRead, receipt_id)
                receipt.status, receipt.error_code, receipt.finished_at = "completed", None, now()
                receipt.sources = source_references(request.capability, result)
            with self.factory.begin() as db:
                authorize_job(db, job)
            return {"status": 200, "body": result}
        except ValidationError:
            return {"status": 400, "body": {"error": "agent_tool_arguments_invalid"}}
        except HTTPException as error:
            return {"status": error.status_code, "body": {"error": error.detail}}

    def finish(self, job, result=None, error=None):
        with self.factory.begin() as db:
            membership = lock_owner(db, job.organization_id, job.owner_id)
            turn = locked_turn(db, job)
            if turn.status != "running" or turn.lease_id != job.lease_id:
                return
            if turn.lease_expires_at <= now():
                error = "agent_lease_lost"
            user = db.get(User, job.owner_id)
            if (
                not user.active
                or not membership.active
                or not membership.licensed
                or not billing_access(db, job.organization_id)
            ):
                error = "agent_access_revoked"
            if turn.cancel_requested:
                error = "agent_cancelled"
            from .project_access import conversation_context_access

            try:
                conversation_context_access(db, db.get(Conversation, turn.conversation_id))
            except HTTPException:
                error = "project_context_revoked"
            if not error and db.get(Conversation, turn.conversation_id).purpose == "onboarding":
                proposals = db.scalars(
                    select(RoutineProposal.id).where(RoutineProposal.conversation_id == turn.conversation_id)
                ).all()
                if len(proposals) < 2:
                    error = "routine_proposals_missing"
            if not error and occurrence_for_turn(db, turn.id):
                capabilities = db.get(Conversation, turn.conversation_id).capabilities
                if not set(capabilities) <= read_evidence(db, turn)[0]:
                    error = "routine_sources_missing"
            if (
                not error
                and (
                    occurrence_for_turn(db, turn.id)
                    or db.scalar(select(RoutineTrial.id).where(RoutineTrial.turn_id == turn.id))
                )
                and not delivery_accepted(db, turn)
            ):
                error = "routine_email_not_accepted"
            turn.finished_at, turn.lease_expires_at = now(), None
            db.execute(
                update(ToolRead)
                .where(ToolRead.turn_id == turn.id, ToolRead.status == "started")
                .values(status="failed", error_code="tool_result_unknown", finished_at=now())
            )
            if error:
                turn.status = "cancelled" if error == "agent_cancelled" else "failed"
                turn.error_code = error
                db.execute(
                    update(ModelCall)
                    .where(ModelCall.turn_id == turn.id, ModelCall.status == "started")
                    .values(status="failed", error_code="model_result_unknown", finished_at=now())
                )
            else:
                turn.status, turn.response = "completed", result["response"]
            finish_occurrence(db, turn, error)
            record_event(db, turn, turn.status)

    def run_once(self):
        self.recover_expired()
        job = self.claim()
        if job is None:
            return False
        try:
            with self.factory.begin() as db:
                authorize_job(db, job)
                turn = db.get(ChatTurn, job.id)
                conversation = db.get(Conversation, turn.conversation_id)
                if (conversation.provider, conversation.model) != (
                    self.settings.model.provider,
                    self.settings.model.model,
                ):
                    raise RuntimeFailure("chat_model_changed")
                payload = {
                    "session_id": conversation.id,
                    "model": conversation.model,
                    "system_prompt": conversation.system_prompt,
                    "capabilities": conversation.capabilities,
                    "message": turn.message,
                    "purpose": conversation.purpose,
                    "documents_enabled": conversation.documents_enabled,
                    "tool_revision": conversation.tool_revision,
                    "email_send_enabled": conversation.email_send_enabled,
                    "activity_enabled": True,
                }
                from .conversation_branches import branch_history

                payload["initial_history"] = branch_history(db, conversation)
                if conversation.tool_revision >= 7:
                    payload["research_enabled"] = bool((conversation.service_features or {}).get("research"))
                    payload["vision_enabled"] = bool((conversation.service_features or {}).get("vision"))
                    payload["state_scope"] = conversation.id
                    payload["project_context_enabled"] = bool(
                        conversation.context_project_id
                    ) and source_allowed(conversation, "project")
                    payload["documents_enabled"] = source_allowed(conversation, "documents")
                    depth = (conversation.work_settings or {}).get("depth", "balanced")
                    payload["max_iterations"] = {"quick": 12, "balanced": 20, "deep": 40}[depth]
                    payload["run_budget_seconds"] = {"quick": 120, "balanced": 240, "deep": 480}[depth]
            handlers = {
                "model": lambda body: self.model(job, body),
                "tool": lambda body: self.tool(job, conversation.capabilities, body),
                "activity": lambda body: self.activity(job, body),
            }
            with self.heartbeat(job) as check:
                runtime = self.runtime
                if isinstance(runtime, ContainerRuntime) and conversation.purpose != "scheduled":
                    runtime = ContainerRuntime(
                        replace(runtime.settings, timeout_seconds=payload.get("run_budget_seconds", 240) + 30)
                    )
                result = runtime.run(
                    job.organization_id,
                    job.owner_id,
                    payload,
                    lambda operation, body: handlers[operation](body),
                    check=check,
                )
                check()
            if (
                not result.get("completed")
                or result.get("failed")
                or result.get("interrupted")
                or len(result["response"]) > 200000
            ):
                raise RuntimeFailure("agent_execution_incomplete")
            self.finish(job, result=result)
        except RuntimeFailure as error:
            self.finish(job, error=str(error))
        except Exception:
            self.finish(job, error="agent_execution_failed")
        return True


def main():
    from .worker_service import main as service_main

    return service_main("chat")


if __name__ == "__main__":
    raise SystemExit(main())
