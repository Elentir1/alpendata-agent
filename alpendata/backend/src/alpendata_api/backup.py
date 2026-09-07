"""Local, quiescent PostgreSQL + owner-state bundles. No remote storage or secrets export."""

import argparse
import hashlib
import io
import json
import os
import stat
import subprocess
import tarfile
from contextlib import ExitStack
from pathlib import Path, PurePosixPath
from uuid import UUID, uuid4

from sqlalchemy import inspect, select, text
from sqlalchemy.exc import SQLAlchemyError

from .database import database_factory
from .file_store import FileStore, FileStoreSettings
from .models import Base, ChatTurn, Conversation, EmailAttempt, FileVersion, Membership, SharePointSave, now
from .runtime import ContainerRuntime, RuntimeFailure, RuntimeSettings, container_name
from .runtime_recovery import RuntimeRecovery


class BackupFailure(Exception):
    pass


def postgres_command(engine, binaries, command, arguments):
    if engine.dialect.name != "postgresql":
        raise BackupFailure("backup_requires_postgresql")
    connection = engine.url.translate_connect_args(username="user", database="dbname")
    connection.update(engine.url.query)
    # Only the selected connection reaches libpq; service/model secrets and inherited
    # PGOPTIONS/PGSERVICE overrides never reach the maintenance subprocess.
    environment = {key: os.environ[key] for key in ("PATH", "LANG") if key in os.environ}
    variables = {
        "dbname": "PGDATABASE",
        "host": "PGHOST",
        "hostaddr": "PGHOSTADDR",
        "port": "PGPORT",
        "user": "PGUSER",
        "password": "PGPASSWORD",
        "sslmode": "PGSSLMODE",
        "sslrootcert": "PGSSLROOTCERT",
        "sslcert": "PGSSLCERT",
        "sslkey": "PGSSLKEY",
        "channel_binding": "PGCHANNELBINDING",
        "connect_timeout": "PGCONNECT_TIMEOUT",
    }
    if set(connection) - variables.keys() or any(
        not isinstance(value, (str, int)) for value in connection.values()
    ):
        raise BackupFailure("backup_connection_option_unsupported")
    environment.update({variables[key]: str(value) for key, value in connection.items() if value is not None})
    environment["PGCONNECT_TIMEOUT"] = "10"
    if command == "pg_restore":
        if "=" in connection["dbname"] or "://" in connection["dbname"]:
            raise BackupFailure("backup_database_name_unsupported")
        arguments = ["--dbname=" + connection["dbname"], *arguments]
    try:
        result = subprocess.run(
            [str(binaries / command), "--no-password", *arguments],
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=3600,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise BackupFailure("backup_postgresql_tool_unavailable") from None
    # Warnings need operator investigation; do not silently certify an incomplete dump.
    if result.returncode or result.stderr:
        raise BackupFailure("backup_postgresql_tool_failed")


def checksum(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def safe_member(info):
    name = PurePosixPath(info.name)
    if name.is_absolute() or ".." in name.parts or len(name.parts) < 2:
        raise BackupFailure("backup_state_path_invalid")
    try:
        offset = 1 if name.parts[0] in ("scoped", "objects") else 0
        boundary = 4 if name.parts[0] == "scoped" else 3 if name.parts[0] == "objects" else 2
        if len(name.parts) < boundary:
            raise ValueError
        for part in name.parts[offset:boundary]:
            if str(UUID(part)) != part:
                raise ValueError
        if name.parts[0] == "objects" and (
            len(name.parts) != 4
            or not info.isfile()
            or len(name.parts[3]) != 64
            or any(c not in "0123456789abcdef" for c in name.parts[3])
        ):
            raise ValueError
    except ValueError:
        raise BackupFailure("backup_state_path_invalid") from None
    if not (info.isfile() or info.isdir() or info.issym()):
        raise BackupFailure("backup_state_type_unsupported")
    if info.issym():
        target = PurePosixPath(info.linkname)
        depth = len(name.parts) - boundary - 1
        if target.is_absolute():
            raise BackupFailure("backup_state_link_unsafe")
        for part in target.parts:
            depth += -1 if part == ".." else 0 if part == "." else 1
            if depth < 0:
                raise BackupFailure("backup_state_link_unsafe")
    # Never restore setuid/setgid, foreign ownership or group/world access.
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    info.mode = (info.mode & 0o700) | (0o700 if info.isdir() else 0o600 if info.isfile() else 0)
    return info


def write_states(archive, states, objects=(), store=None):
    with tarfile.open(archive, "w", dereference=False) as bundle:
        for organization, owner, state in states:
            for directory, folders, files in os.walk(state, followlinks=False):
                for name in ["", *sorted(folders), *sorted(files)]:
                    path = Path(directory) / name if name else Path(directory)
                    if name in folders and not path.is_symlink():
                        continue  # The directory is added when os.walk visits it.
                    relative = Path(organization) / owner / path.relative_to(state)
                    info = safe_member(bundle.gettarinfo(str(path), arcname=relative.as_posix()))
                    if info.isfile():
                        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
                        with os.fdopen(descriptor, "rb") as content:
                            if not stat.S_ISREG(os.fstat(content.fileno()).st_mode):
                                raise BackupFailure("backup_state_type_unsupported")
                            bundle.addfile(info, content)
                    else:
                        bundle.addfile(info)
        for key in objects:
            data = store.get(key)
            info = tarfile.TarInfo("objects/" + key)
            info.size, info.mode = len(data), 0o600
            bundle.addfile(safe_member(info), io.BytesIO(data))


def create_bundle(engine, runtime, destination, binaries, revision, *, store=None):
    if engine.dialect.name != "postgresql":
        raise BackupFailure("backup_requires_postgresql")
    if len(revision) != 40 or any(c not in "0123456789abcdef" for c in revision):
        raise BackupFailure("backup_revision_invalid")
    root = runtime.settings.state_root.resolve()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination = destination.absolute()
    if destination.resolve().is_relative_to(root) or root.is_relative_to(destination.resolve()):
        raise BackupFailure("backup_destination_overlaps_state")
    destination.mkdir(mode=0o700, parents=False, exist_ok=False)
    receipt = {
        "format": 1,
        "backup_id": str(uuid4()),
        "created_at": now(),
        "revision": revision,
        "runtime_image": runtime.settings.image,
    }
    # The final manifest is written only after both stores have been copied successfully.
    with engine.begin() as connection, ExitStack() as locks:
        tables = set(inspect(connection).get_table_names(schema="public"))
        if tables != set(Base.metadata.tables) | {"alembic_version"}:
            raise BackupFailure("backup_schema_unexpected")
        names = ", ".join('public."' + name + '"' for name in sorted(tables))
        connection.execute(text(f"LOCK TABLE {names} IN SHARE MODE NOWAIT"))
        for model, statuses in (
            (ChatTurn, ["running"]),
            (EmailAttempt, ["sending"]),
            (SharePointSave, ["running"]),
        ):
            if connection.execute(select(model.id).where(model.status.in_(statuses)).limit(1)).first():
                raise BackupFailure("backup_execution_active")
        members = connection.execute(
            select(Membership.organization_id, Membership.user_id).order_by(
                Membership.organization_id, Membership.user_id
            )
        ).all()
        states = []
        recovery = RuntimeRecovery(runtime, None)
        for organization, owner in members:
            state = locks.enter_context(runtime.owner_state(organization, owner))
            if recovery.snapshot(container_name(organization, owner), state) is not None:
                raise BackupFailure("backup_container_present")
            states.append((organization, owner, state))
        known = {(organization, owner) for organization, owner in members}
        scoped = connection.execute(
            select(Conversation.organization_id, Conversation.owner_id, Conversation.id).where(
                Conversation.tool_revision >= 7
            )
        ).all()
        for organization, owner, identifier in scoped:
            state = locks.enter_context(runtime.owner_state(organization, owner, identifier))
            if recovery.snapshot(container_name(organization, owner, identifier), state) is not None:
                raise BackupFailure("backup_container_present")
            states.append(("scoped/" + organization, owner + "/" + identifier, state))
        scoped_root = root / "scoped"
        known_scopes = set(scoped)
        if scoped_root.exists():
            if scoped_root.is_symlink() or not scoped_root.is_dir():
                raise BackupFailure("backup_state_layout_invalid")
            for organization in scoped_root.iterdir():
                if organization.name == "locks":
                    continue
                if organization.is_symlink() or not organization.is_dir():
                    raise BackupFailure("backup_state_layout_invalid")
                for owner in organization.iterdir():
                    if owner.is_symlink() or not owner.is_dir():
                        raise BackupFailure("backup_state_layout_invalid")
                    for scope in owner.iterdir():
                        if (organization.name, owner.name, scope.name) not in known_scopes:
                            raise BackupFailure("backup_state_owner_unknown")
        for organization in root.iterdir():
            if organization.name in ("locks", "scoped", "objects"):
                continue
            if not organization.is_dir() or organization.is_symlink():
                raise BackupFailure("backup_state_layout_invalid")
            for owner in organization.iterdir():
                if (organization.name, owner.name) not in known:
                    raise BackupFailure("backup_state_owner_unknown")
        receipt["schema"] = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        snapshot = connection.execute(text("SELECT pg_export_snapshot()")).scalar_one()
        postgres_command(
            engine,
            binaries,
            "pg_dump",
            [
                "--format=custom",
                "--no-owner",
                "--no-acl",
                "--snapshot=" + snapshot,
                "--file=" + str(destination / "database.dump"),
            ],
        )
        objects = connection.execute(select(FileVersion.object_key).distinct()).scalars().all()
        if scoped or objects:
            receipt["format"] = 2
        store = store or FileStore(FileStoreSettings(root=root / "objects"))
        write_states(destination / "states.tar", states, objects, store)
        receipt["owners"] = len(members)
        receipt["files"] = {
            name: {"sha256": checksum(destination / name), "bytes": (destination / name).stat().st_size}
            for name in ("database.dump", "states.tar")
        }
        for name in receipt["files"]:
            (destination / name).chmod(0o600)
        (destination / "manifest.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        (destination / "manifest.json").chmod(0o600)
    return receipt


def main():
    parser = argparse.ArgumentParser(description="AlpenData local backup and isolated restoration")
    parser.add_argument("action", choices=("create", "restore"))
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--postgresql-bin", type=Path, default=Path("/usr/lib/postgresql/17/bin"))
    parser.add_argument("--revision", help="Full source commit SHA for create")
    args = parser.parse_args()
    engine = None
    try:
        os.umask(0o077)
        engine, factory = database_factory(os.environ["ALPENDATA_DATABASE_URL"])
        if args.action == "create":
            runtime = ContainerRuntime(
                RuntimeSettings(
                    Path(os.environ["ALPENDATA_RUNTIME_STATE_ROOT"]), os.environ["ALPENDATA_RUNTIME_IMAGE"]
                )
            )
            # Backups need storage credentials, never a model or OAuth configuration.
            storage = (
                FileStoreSettings(
                    swift_container_url=os.environ["ALPENDATA_SWIFT_CONTAINER_URL"],
                    swift_token=os.environ.get("ALPENDATA_SWIFT_TOKEN", ""),
                )
                if os.environ.get("ALPENDATA_SWIFT_CONTAINER_URL")
                else FileStoreSettings(
                    root=Path(
                        os.environ.get("ALPENDATA_FILE_STORE_ROOT") or runtime.settings.state_root / "objects"
                    )
                )
            )
            result = create_bundle(
                engine,
                runtime,
                args.bundle,
                args.postgresql_bin,
                args.revision or "",
                store=FileStore(storage),
            )
        else:
            from .backup_restore import restore_bundle

            result = restore_bundle(
                engine,
                factory,
                args.bundle,
                Path(os.environ["ALPENDATA_RUNTIME_STATE_ROOT"]),
                args.postgresql_bin,
            )
        print(
            json.dumps(
                {
                    "status": "created" if args.action == "create" else "restored_suspended",
                    "backup_id": result["backup_id"],
                }
            )
        )
    except (BackupFailure, RuntimeFailure) as error:
        print(json.dumps({"status": "refused", "error": str(error)}))
        return 1
    except (OSError, SQLAlchemyError, ValueError, KeyError, tarfile.TarError):
        print(json.dumps({"status": "refused", "error": "backup_operation_failed"}))
        return 1
    finally:
        if engine is not None:
            engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
