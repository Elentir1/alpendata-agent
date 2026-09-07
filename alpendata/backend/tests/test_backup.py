"""Real PostgreSQL dumps/restores and OCI state locks; all identities/data are synthetic."""

import base64
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError
from test_documents import example_pdf, start_document_turn
from test_routines import connected_service as connected_service
from test_routines import routine_service as routine_service
from test_runtime_recovery import orphan
from test_schedules import activation
from test_schedules import approved_trial as approved_trial

from alpendata_api.app import create_app
from alpendata_api.auth import issue_session
from alpendata_api.backup import BackupFailure, checksum, create_bundle
from alpendata_api.backup_restore import restore_bundle, verify_bundle
from alpendata_api.database import database_factory
from alpendata_api.models import ChatTurn, MicrosoftConnection, RoutineSchedule, User
from alpendata_api.runtime import ContainerRuntime, RuntimeFailure, RuntimeSettings
from alpendata_api.runtime_recovery import RuntimeRecovery
from alpendata_api.schedule_worker import ScheduleWorker
from alpendata_api.workspace_files import file_store

pytestmark = pytest.mark.linux_only


@pytest.fixture
def backup_host(request):
    image, binaries = (
        request.config.getoption("--runtime-image"),
        request.config.getoption("--postgresql-bin"),
    )
    if not image or not binaries:
        pytest.skip("Requires real OCI image and disposable PostgreSQL")
    with tempfile.TemporaryDirectory(prefix="alpendata-backup-") as temporary:
        root = Path(temporary)
        yield root, ContainerRuntime(RuntimeSettings(root / "source", image)), Path(binaries)


def empty_target(engine):
    name = "restore_" + uuid4().hex
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.exec_driver_sql('CREATE DATABASE "' + name + '" TEMPLATE template0')
    return database_factory(engine.url.set(database=name).render_as_string(hide_password=False))


def test_bundle_restores_both_stores_without_replaying_work_or_reusing_sessions(
    routine_service,
    approved_trial,
    backup_host,
):
    app, client, settings, _, _, org, admin, owner = routine_service
    root, runtime, binaries = backup_host
    trial, worker = approved_trial
    base = f"/api/organizations/{org}"
    schedule = client.post(base + "/schedules", headers=owner[2], json=activation(trial)).json()
    path = start_document_turn(routine_service)
    job = worker.claim()
    content = example_pdf()
    artifact = worker.tool(
        job,
        [],
        {"kind": "document", "filename": "Session.pdf", "content_base64": base64.b64encode(content).decode()},
    )["body"]
    with pytest.raises(BackupFailure, match="backup_execution_active"):
        create_bundle(app.state.engine, runtime, root / "active", binaries, "a" * 40)
    worker.finish(job, result={"response": "Document ready"})
    # Populate memory through the real Hermes memory operation, not a substitute file format.
    memory = runtime.run(org, owner[0], {"operation": "memory", "action": "read"}, lambda *_: None)
    assert "memory" in memory
    memory = runtime.run(
        org,
        owner[0],
        {
            "operation": "memory",
            "action": "update",
            "target": "memory",
            "version": memory["memory"]["memory"]["version"],
            "entries": ["Private coaching preference"],
        },
        lambda *_: None,
    )
    assert "memory_error" not in memory, memory
    with runtime.owner_state(org, owner[0]) as state:
        (state / "workspace").mkdir(exist_ok=True)
        (state / "workspace" / "private.pdf").write_bytes(content)
        (state / "workspace" / "relative.pdf").symlink_to("private.pdf")
    queued = client.post(
        path + "/turns", headers=owner[2], json={"request_id": str(uuid4()), "message": "A pending task"}
    ).json()
    file = client.post(
        path + "/files",
        headers=owner[2],
        json={
            "request_id": str(uuid4()),
            "filename": "backup.txt",
            "content_base64": base64.b64encode(b"Immutable private attachment").decode(),
        },
    ).json()
    conversation_id = path.rsplit("/", 1)[-1]
    scoped = runtime.run(
        org,
        owner[0],
        {"operation": "memory", "action": "read", "state_scope": conversation_id},
        lambda *_: None,
    )
    scoped = runtime.run(
        org,
        owner[0],
        {
            "operation": "memory",
            "action": "update",
            "state_scope": conversation_id,
            "target": "memory",
            "version": scoped["memory"]["memory"]["version"],
            "entries": ["Scoped private client fact"],
        },
        lambda *_: None,
    )
    assert "memory_error" not in scoped
    bundle = root / "bundle"
    receipt = create_bundle(app.state.engine, runtime, bundle, binaries, "a" * 40, store=file_store(settings))
    assert receipt["format"] == 2
    assert receipt == verify_bundle(bundle)
    assert "Private coaching" not in json.dumps(receipt)
    assert bundle.stat().st_mode & 0o077 == 0
    # Later source changes must not leak backwards into the saved owner files.
    (state / "workspace" / "private.pdf").write_bytes(b"Later source change")
    target_engine, factory = empty_target(app.state.engine)
    target = root / "restored"
    try:
        restored = restore_bundle(target_engine, factory, bundle, target, binaries)
        assert restored["status"] == "restored_suspended"
        scoped_memory = (
            target / "scoped" / org / owner[0] / conversation_id / ".hermes" / "memories" / "MEMORY.md"
        )
        assert "Scoped private client fact" in scoped_memory.read_text()
        assert (target / org / owner[0] / "workspace" / "relative.pdf").read_bytes() == content
        with factory() as db:
            assert db.get(ChatTurn, queued["id"]).status == "interrupted"
            paused = db.get(RoutineSchedule, schedule["id"])
            assert paused.status == "paused" and paused.next_run_at is None
            assert all(
                c.status == "disconnected" and c.encrypted_cache is None
                for c in db.scalars(select(MicrosoftConnection))
            )
        restored_settings = replace(
            settings,
            database_url=target_engine.url.render_as_string(hide_password=False),
            runtime=replace(runtime.settings, state_root=target),
        )
        restored_app = create_app(restored_settings)
        with TestClient(restored_app, base_url=settings.public_origin) as restored_client:
            assert restored_client.get("/api/me", headers=owner[2]).status_code == 401
            with restored_app.state.session_factory.begin() as db:
                new_owner = {"Authorization": "Bearer " + issue_session(db, db.get(User, owner[0]), 3600)}
                new_admin = {"Authorization": "Bearer " + issue_session(db, db.get(User, admin[0]), 3600)}
            restored_file = base + "/files/" + file["id"] + "/versions/1/content"
            assert (
                restored_client.get(restored_file, headers=new_owner).content
                == b"Immutable private attachment"
            )
            assert restored_client.get(restored_file, headers=new_admin).status_code == 404
            download = base + "/documents/" + artifact["id"] + "/download"
            assert restored_client.get(download, headers=new_owner).content == content
            assert restored_client.get(download, headers=new_admin).status_code == 404
            restored_memory = restored_client.get(base + "/memory", headers=new_owner)
            assert restored_memory.status_code == 200, restored_memory.text
            assert restored_memory.json()["memory"]["entries"] == ["Private coaching preference"]
            assert restored_client.get(path, headers=new_admin).status_code == 404
            assert ScheduleWorker(restored_settings, restored_app.state.session_factory).tick() == 0
        with pytest.raises(BackupFailure, match="restore_state_destination_exists"):
            restore_bundle(target_engine, factory, bundle, target, binaries)
        with pytest.raises(BackupFailure, match="restore_database_not_empty"):
            restore_bundle(target_engine, factory, bundle, root / "another", binaries)
        assert not (root / "another").exists()
    finally:
        target_engine.dispose()
    # The source connection and queued work were never revoked by the maintenance tool.
    assert client.get("/api/me", headers=owner[2]).status_code == 200
    with app.state.session_factory() as db:
        assert db.get(ChatTurn, queued["id"]).status == "queued"


def test_backup_refuses_writers_orphans_unsafe_links_and_corruption_without_a_complete_manifest(
    routine_service,
    backup_host,
):
    app, client, _, _, _, org, _, owner = routine_service
    root, runtime, binaries = backup_host
    engine = app.state.engine
    with engine.begin() as writer:
        writer.execute(text("UPDATE alpendata_organizations SET name = name WHERE id = :id"), {"id": org})
        with pytest.raises(OperationalError):
            create_bundle(engine, runtime, root / "writer", binaries, "a" * 40)
    assert not (root / "writer" / "manifest.json").exists()
    with runtime.owner_state(org, owner[0]) as state:
        with pytest.raises(RuntimeFailure, match="agent_already_running"):
            create_bundle(engine, runtime, root / "owner-busy", binaries, "a" * 40)
    recovery = RuntimeRecovery(runtime, app.state.session_factory)
    identifier = orphan(recovery, org, owner[0], state)
    try:
        with pytest.raises(BackupFailure, match="backup_container_present"):
            create_bundle(engine, runtime, root / "orphan", binaries, "a" * 40)
    finally:
        recovery.engine(["rm", "--force", identifier], timeout=30)
    (state / "escape").symlink_to(root / "outside")
    with pytest.raises(BackupFailure, match="backup_state_link_unsafe"):
        create_bundle(engine, runtime, root / "unsafe", binaries, "a" * 40)
    assert not (root / "unsafe" / "manifest.json").exists()
    (state / "escape").unlink()
    environment = {key: os.environ[key] for key in ("PATH", "HOME", "XDG_RUNTIME_DIR") if key in os.environ}
    environment.update(
        ALPENDATA_DATABASE_URL=engine.url.render_as_string(hide_password=False),
        ALPENDATA_RUNTIME_STATE_ROOT=str(runtime.settings.state_root),
        ALPENDATA_RUNTIME_IMAGE=runtime.settings.image,
    )
    bundle = root / "cli"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "alpendata_api.backup",
            "create",
            "--bundle",
            str(bundle),
            "--postgresql-bin",
            str(binaries),
            "--revision",
            "a" * 40,
        ],
        env=environment,
        capture_output=True,
        text=True,
        timeout=45,
        check=True,
    )
    assert json.loads(result.stdout)["status"] == "created"
    with (bundle / "states.tar").open("ab") as stream:
        stream.write(b"corruption")
    target_engine, factory = empty_target(engine)
    try:
        with pytest.raises(BackupFailure, match="backup_integrity_failed"):
            restore_bundle(target_engine, factory, bundle, root / "corrupt-restore", binaries)
        assert not (root / "corrupt-restore").exists()
        # Even a matching manifest never permits an archive to escape the target owner.
        with tarfile.open(bundle / "states.tar", "w") as archive:
            link = tarfile.TarInfo(org + "/" + owner[0] + "/escape")
            link.type, link.linkname = tarfile.SYMTYPE, "../../outside"
            archive.addfile(link)
        manifest = json.loads((bundle / "manifest.json").read_text())
        manifest["files"]["states.tar"] = {
            "sha256": checksum(bundle / "states.tar"),
            "bytes": (bundle / "states.tar").stat().st_size,
        }
        (bundle / "manifest.json").write_text(json.dumps(manifest))
        with pytest.raises(BackupFailure, match="backup_state_link_unsafe"):
            restore_bundle(target_engine, factory, bundle, root / "escape-restore", binaries)
        assert not (root / "outside").exists()
        assert (root / "escape-restore" / "RESTORE_INCOMPLETE").exists()
        with target_engine.connect() as connection:
            assert connection.execute(text("SELECT to_regclass('alpendata_users')")).scalar() is None
    finally:
        target_engine.dispose()
