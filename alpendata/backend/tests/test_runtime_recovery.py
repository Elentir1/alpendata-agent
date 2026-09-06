"""Real rootless orphan containers, PostgreSQL locks and operator CLI; no external services."""

import json
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest

from alpendata_api.models import ChatTurn, Conversation, EmailAttempt, EmailDraft, ModelCall, now
from alpendata_api.runtime import ContainerRuntime, RuntimeFailure, RuntimeSettings, container_name
from alpendata_api.runtime_recovery import RuntimeRecovery

pytestmark = pytest.mark.linux_only


@pytest.fixture
def recovery(service, request):
    image = request.config.getoption("--runtime-image")
    if not image or not request.config.getoption("--postgresql-bin"):
        pytest.skip("Requires real OCI image and disposable PostgreSQL")
    with tempfile.TemporaryDirectory(prefix="alpendata-recovery-") as root:
        runtime = ContainerRuntime(RuntimeSettings(Path(root), image))
        yield RuntimeRecovery(runtime, service[0].state.session_factory)


def orphan(recovery, org, owner, state):
    args = recovery.runtime.command(container_name(org, owner), state)
    # Retain the production isolation options, but detach a harmless long-lived process.
    args.remove("--interactive")
    args.insert(args.index("run") + 1, "--detach")
    args[-1:-1] = ["--entrypoint", "/opt/venv/bin/python"]
    args.extend(["-c", "import time; time.sleep(600)"])
    result = subprocess.run(args, capture_output=True, text=True, check=True, timeout=30)
    return result.stdout.strip()


def test_recovery_fences_live_work_preserves_receipts_and_never_replays(service, account, recovery):
    app, client = service
    owner, headers = account("owner@example.com")
    org = client.post("/api/organizations", headers=headers, json={"name": "Coaches"}).json()["id"]
    with app.state.session_factory.begin() as db:
        conversation = Conversation(
            organization_id=org,
            owner_id=owner,
            title="Private title",
            language="fr",
            provider="mistral",
            model="synthetic",
            system_prompt="Private context",
        )
        db.add(conversation)
        db.flush()
        turn = ChatTurn(
            organization_id=org,
            owner_id=owner,
            conversation_id=conversation.id,
            request_id=str(uuid4()),
            sequence=1,
            message="Private message",
            status="running",
            lease_id=str(uuid4()),
            lease_expires_at=now() + 120,
        )
        db.add(turn)
        db.flush()
        call = ModelCall(
            organization_id=org, owner_id=owner, turn_id=turn.id, provider="mistral", model="synthetic"
        )
        draft = EmailDraft(
            organization_id=org,
            owner_id=owner,
            turn_id=turn.id,
            initial_hash="a" * 64,
            message={"subject": "Private subject"},
        )
        db.add_all([call, draft])
        db.flush()
        attempt = EmailAttempt(
            organization_id=org,
            owner_id=owner,
            draft_id=draft.id,
            version=1,
            message=draft.message,
            status="unknown",
            error_code="email_send_unknown",
        )
        db.add(attempt)
        db.flush()
        turn_id, call_id, attempt_id = turn.id, call.id, attempt.id
    with recovery.runtime.owner_state(org, owner) as state:
        (state / "personal.txt").write_text("Private memory stays intact")
    identifier = orphan(recovery, org, owner, state)
    try:
        snapshot = recovery.inspect_or_recover(org, owner)
        assert snapshot["container"]["id"] == identifier
        assert "Private" not in json.dumps(snapshot)
        with pytest.raises(RuntimeFailure, match="recovery_execution_pending"):
            recovery.inspect_or_recover(org, owner, expected_container=identifier)
        with app.state.session_factory.begin() as db:
            db.get(ChatTurn, turn_id).lease_expires_at = now() - 1
        with recovery.runtime.owner_state(org, owner):
            with pytest.raises(RuntimeFailure, match="agent_already_running"):
                recovery.inspect_or_recover(org, owner, expected_container=identifier)
        with pytest.raises(RuntimeFailure, match="recovery_inspection_changed"):
            recovery.inspect_or_recover(org, owner, expected_container="0" * 64)

        def recover():
            try:
                return recovery.inspect_or_recover(org, owner, expected_container=identifier)
            except RuntimeFailure as error:
                return str(error)

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(recover) for _ in range(2)]
            results = [f.result(timeout=45) for f in futures]
        succeeded = [r for r in results if isinstance(r, dict)]
        assert len(succeeded) == 1 and succeeded[0]["interrupted_turns"] == [turn_id]
        refused = [r for r in results if isinstance(r, str)]
        assert len(refused) == 1 and refused[0] in {"recovery_inspection_changed", "recovery_owner_busy"}
        assert recovery.inspect_or_recover(org, owner)["container"] is None
        with app.state.session_factory() as db:
            turn, call, attempt = (
                db.get(ChatTurn, turn_id),
                db.get(ModelCall, call_id),
                db.get(EmailAttempt, attempt_id),
            )
            assert turn.status == "interrupted" and turn.lease_expires_at is None
            assert call.status == "failed" and call.total_tokens is None
            assert attempt.status == "unknown" and attempt.message == {"subject": "Private subject"}
        assert (state / "personal.txt").read_text() == "Private memory stays intact"
        # A new real runtime operation can now use the private volume without a model.
        result = recovery.runtime.run(
            org,
            owner,
            {"operation": "memory", "action": "read"},
            lambda *_: pytest.fail("Recovery must not call a broker"),
        )
        assert "memory" in result
    finally:
        recovery.engine(["rm", "--force", "--ignore", identifier], timeout=20)


def test_operator_cli_rechecks_identity_mount_and_pending_queue(service, account, recovery, database_url):
    app, client = service
    owner, headers = account("owner@example.com")
    org = client.post("/api/organizations", headers=headers, json={"name": "Coaches"}).json()["id"]
    with recovery.runtime.owner_state(org, owner) as state:
        foreign = state.parent / str(uuid4())
        foreign.mkdir()
    identifier = orphan(recovery, org, owner, foreign)
    try:
        with pytest.raises(RuntimeFailure, match="recovery_container_mismatch"):
            recovery.inspect_or_recover(org, owner, expected_container=identifier)
        assert recovery.engine(["container", "exists", identifier]).returncode == 0
    finally:
        recovery.engine(["rm", "--force", "--ignore", identifier], timeout=20)
    old_identifier = identifier
    identifier = orphan(recovery, org, owner, state)
    environment = {
        **os.environ,
        "ALPENDATA_DATABASE_URL": database_url,
        "ALPENDATA_RUNTIME_STATE_ROOT": str(recovery.runtime.settings.state_root),
        "ALPENDATA_RUNTIME_IMAGE": recovery.runtime.settings.image,
    }

    def cli(action, *extra):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "alpendata_api.runtime_recovery",
                action,
                "--organization",
                org,
                "--owner",
                owner,
                *extra,
            ],
            env=environment,
            capture_output=True,
            text=True,
            timeout=35,
        )
        return result.returncode, json.loads(result.stdout)

    try:
        code, inspected = cli("inspect")
        assert code == 0 and inspected["container"]["id"] == identifier
        code, refused = cli("recover", "--expected-container", old_identifier)
        assert code == 1 and refused["error"] == "recovery_inspection_changed"
        with app.state.session_factory.begin() as db:
            conversation = Conversation(
                organization_id=org,
                owner_id=owner,
                title="Private title",
                language="fr",
                provider="mistral",
                model="synthetic",
                system_prompt="Private",
            )
            db.add(conversation)
            db.flush()
            turn = ChatTurn(
                organization_id=org,
                owner_id=owner,
                conversation_id=conversation.id,
                request_id=str(uuid4()),
                sequence=1,
                message="Pending",
                status="queued",
            )
            db.add(turn)
            db.flush()
            turn_id = turn.id
        code, refused = cli("recover", "--expected-container", identifier)
        assert code == 1 and refused["error"] == "recovery_execution_pending"
        with app.state.session_factory.begin() as db:
            db.get(ChatTurn, turn_id).status = "cancelled"
        code, recovered = cli("recover", "--expected-container", identifier)
        assert code == 0 and recovered["status"] == "recovered"
        assert recovered["interrupted_turns"] == []
        assert cli("inspect")[1]["container"] is None
        # Simulate a committed container removal followed by a database rollback.
        with app.state.session_factory.begin() as db:
            turn = db.get(ChatTurn, turn_id)
            turn.status, turn.lease_expires_at = "running", now() - 1
        code, recovered = cli("recover", "--expected-container", "absent")
        assert code == 0 and recovered["interrupted_turns"] == [turn_id]
        with app.state.session_factory() as db:
            assert db.get(ChatTurn, turn_id).status == "interrupted"
    finally:
        recovery.engine(["rm", "--force", "--ignore", identifier], timeout=20)
