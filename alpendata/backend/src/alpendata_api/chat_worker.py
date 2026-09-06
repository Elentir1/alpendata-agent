"""Durable chat worker. PostgreSQL owns jobs; each Hermes state stays private."""

import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Literal
from uuid import uuid4

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import select, update

from .artifacts import publish_document
from .connections import MicrosoftReader, SearchInput, lock_member
from .database import database_factory
from .graph_documents import FileInput
from .model_gateway import ModelError, ModelGateway
from .models import ChatTurn, Conversation, Membership, ModelCall, RoutineProposal, ToolRead, User, now
from .routine_service import read_evidence, record_proposals, source_references
from .runtime import ContainerRuntime, RuntimeFailure
from .schedule_state import finish_occurrence, occurrence_for_turn, scheduled_turn_error
from .settings import Settings

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
    scheduled_error = scheduled_turn_error(db, turn)
    if scheduled_error:
        raise RuntimeFailure(scheduled_error)
    return user


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
                turn.status, turn.error_code, turn.finished_at = (
                    "interrupted",
                    "agent_worker_interrupted",
                    now(),
                )
                turn.lease_expires_at = None
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
        # No automatic replay: an interrupted tool may already have taken effect.

    def claim(self):
        with self.factory.begin() as db:
            queued = (
                select(ChatTurn.id)
                .where(
                    ChatTurn.organization_id == Membership.organization_id,
                    ChatTurn.owner_id == Membership.user_id,
                    ChatTurn.status == "queued",
                )
                .exists()
            )
            running = (
                select(ChatTurn.id)
                .where(
                    ChatTurn.organization_id == Membership.organization_id,
                    ChatTurn.owner_id == Membership.user_id,
                    ChatTurn.status == "running",
                )
                .exists()
            )
            membership = db.scalar(
                select(Membership)
                .where(queued, ~running)
                .order_by(Membership.organization_id, Membership.user_id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if membership is None:
                return None
            turn = db.scalar(
                select(ChatTurn)
                .where(
                    ChatTurn.organization_id == membership.organization_id,
                    ChatTurn.owner_id == membership.user_id,
                    ChatTurn.status == "queued",
                )
                .order_by(ChatTurn.created_at, ChatTurn.id)
                .with_for_update()
                .limit(1)
            )
            turn.status, turn.lease_id = "running", str(uuid4())
            turn.started_at, turn.lease_expires_at = now(), now() + LEASE_SECONDS
            return Job(turn.id, turn.organization_id, turn.owner_id, turn.lease_id)

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
                        if not user.active or not membership.active or not membership.licensed:
                            reason[0] = "agent_access_revoked"
                            interrupted.set()
                        if turn.cancel_requested:
                            reason[0] = "agent_cancelled"
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
        try:
            result = self.gateway.complete(payload)
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

    def tool(self, job, capabilities, payload):
        with self.factory.begin() as db:
            authorize_job(db, job)
        try:
            handlers = {
                "routine_proposals": self.proposals_tool,
                "document": self.document_tool,
                "mail_draft": self.email_draft_tool,
                "mail_send": self.email_send_tool,
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
                    if db.get(Conversation, turn.conversation_id).tool_revision < 2:
                        raise HTTPException(403, "document_new_conversation_required")
                arguments = FileInput.model_validate(arguments).model_dump()
            elif request.capability == "files":
                arguments = SearchInput.model_validate(arguments).model_dump()
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
                result = self.microsoft.read(
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
            if not user.active or not membership.active or not membership.licensed:
                error = "agent_access_revoked"
            if turn.cancel_requested:
                error = "agent_cancelled"
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
                }
            handlers = {
                "model": lambda body: self.model(job, body),
                "tool": lambda body: self.tool(job, conversation.capabilities, body),
            }
            with self.heartbeat(job) as check:
                result = self.runtime.run(
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
    settings = Settings.from_environment()
    engine, factory = database_factory(settings.database_url)
    try:
        worker = ChatWorker(settings, factory)
        while True:
            if not worker.run_once():
                time.sleep(1)
    except KeyboardInterrupt:
        return
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
