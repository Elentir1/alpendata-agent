"""Restore a trusted operator bundle into unused stores; never start services or replay work."""

import json
import shutil
import sys
import tarfile
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import delete, inspect, text, update

from .backup import BackupFailure, checksum, postgres_command, safe_member
from .models import (
    AuthSession,
    Base,
    ChatTurn,
    EmailAttempt,
    Invitation,
    InvitationProof,
    MicrosoftConnection,
    MicrosoftConnectionFlow,
    ModelCall,
    PersonalActionPolicy,
    RoutineSchedule,
    SharePointSave,
    SignInFlow,
    ToolRead,
    now,
)


def verify_bundle(bundle):
    for name in ("manifest.json", "database.dump", "states.tar"):
        path = bundle / name
        if path.is_symlink() or not path.is_file():
            raise BackupFailure("backup_bundle_incomplete")
    if (bundle / "manifest.json").stat().st_size > 1024 * 1024:
        raise BackupFailure("backup_manifest_invalid")
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    if manifest["format"] != 1 or set(manifest["files"]) != {"database.dump", "states.tar"}:
        raise BackupFailure("backup_manifest_invalid")
    for name, record in manifest["files"].items():
        if (bundle / name).stat().st_size != record["bytes"] or checksum(bundle / name) != record["sha256"]:
            raise BackupFailure("backup_integrity_failed")
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    if manifest["schema"] != ScriptDirectory.from_config(config).get_current_head():
        raise BackupFailure("backup_schema_version_mismatch")
    return manifest


def extract_states(archive, destination):
    with tarfile.open(archive, "r:") as bundle:
        seen = set()
        for info in bundle:
            safe_member(info)
            if info.name in seen:
                raise BackupFailure("backup_state_duplicate")
            seen.add(info.name)
            path = destination / info.name
            if any(parent.is_symlink() for parent in path.parents if parent != destination.parent):
                raise BackupFailure("backup_state_link_unsafe")
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            if info.isdir():
                path.mkdir(mode=0o700, exist_ok=True)
            elif info.issym():
                path.symlink_to(info.linkname)
            else:
                with bundle.extractfile(info) as source, path.open("xb") as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
                path.chmod(info.mode)


def suspend_restored_work(factory):
    at = now()
    with factory.begin() as db:
        db.execute(update(AuthSession).values(revoked=True))
        for model in (SignInFlow, MicrosoftConnectionFlow, InvitationProof):
            db.execute(delete(model))
        db.execute(update(Invitation).values(revoked=True))
        db.execute(
            update(Invitation)
            .where(Invitation.delivery_status == "sending")
            .values(delivery_status="unknown")
        )
        db.execute(
            update(MicrosoftConnection).values(
                status="disconnected",
                encrypted_cache=None,
                capabilities=[],
                connected_at=None,
                generation=MicrosoftConnection.generation + 1,
            )
        )
        db.execute(
            update(PersonalActionPolicy).values(
                email_mode="confirm",
                version=PersonalActionPolicy.version + 1,
                updated_at=at,
            )
        )
        db.execute(
            update(RoutineSchedule)
            .where(RoutineSchedule.status != "archived")
            .values(
                status="paused",
                next_run_at=None,
                version=RoutineSchedule.version + 1,
                updated_at=at,
                reason_code=None,
            )
        )
        db.execute(
            update(ChatTurn)
            .where(ChatTurn.status.in_(["queued", "running"]))
            .values(
                status="interrupted",
                error_code="agent_worker_interrupted",
                finished_at=at,
                lease_expires_at=None,
            )
        )
        for model, code in ((ModelCall, "model_result_unknown"), (ToolRead, "tool_result_unknown")):
            db.execute(
                update(model)
                .where(model.status == "started")
                .values(
                    status="failed",
                    error_code=code,
                    finished_at=at,
                )
            )
        for model, status in ((EmailAttempt, "sending"), (SharePointSave, "running")):
            db.execute(update(model).where(model.status == status).values(status="unknown", finished_at=at))


def restore_bundle(engine, factory, bundle, destination, binaries):
    if sys.platform != "linux":
        raise BackupFailure("restore_requires_linux")
    if engine.dialect.name != "postgresql":
        raise BackupFailure("backup_requires_postgresql")
    manifest = verify_bundle(bundle)
    destination = destination.absolute()
    if destination.exists() or destination.is_symlink():
        raise BackupFailure("restore_state_destination_exists")
    if destination.resolve().is_relative_to(bundle.resolve()):
        raise BackupFailure("restore_destination_overlaps_bundle")
    with engine.connect() as connection:
        tables = connection.execute(
            text(
                "SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname NOT IN ('pg_catalog','information_schema') "
                "AND n.nspname NOT LIKE 'pg_toast%' AND c.relkind IN ('r','p','v','m','S','f') LIMIT 1"
            )
        ).first()
        if tables:
            raise BackupFailure("restore_database_not_empty")
    # Reserve a new directory first. Failures leave inspectable partial stores; no overwrite/cleanup.
    destination.mkdir(mode=0o700, parents=False, exist_ok=False)
    (destination / "RESTORE_INCOMPLETE").write_text(manifest["backup_id"], encoding="utf-8")
    extract_states(bundle / "states.tar", destination)
    postgres_command(
        engine,
        binaries,
        "pg_restore",
        ["--single-transaction", "--exit-on-error", "--no-owner", "--no-acl", str(bundle / "database.dump")],
    )
    with engine.connect() as connection:
        if set(inspect(connection).get_table_names()) != set(Base.metadata.tables) | {"alembic_version"}:
            raise BackupFailure("restore_schema_unexpected")
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        if version != manifest["schema"]:
            raise BackupFailure("restore_schema_unexpected")
    suspend_restored_work(factory)
    # The receipt stays outside the owner tree; it is not part of any personal runtime mount.
    receipt = {
        "backup_id": manifest["backup_id"],
        "restored_at": now(),
        "status": "restored_suspended",
        "revision": manifest["revision"],
        "runtime_image": manifest["runtime_image"],
    }
    receipt_path = destination.parent / (destination.name + ".restore.json")
    with receipt_path.open("x", encoding="utf-8") as output:
        output.write(json.dumps(receipt, indent=2) + "\n")
    receipt_path.chmod(0o600)
    (destination / "RESTORE_INCOMPLETE").unlink()
    return receipt
