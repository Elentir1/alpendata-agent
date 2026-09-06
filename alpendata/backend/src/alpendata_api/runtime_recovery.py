"""Local operator recovery: no public route, content access, or execution replay."""

import argparse
import json
import os
import re
import subprocess
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from .chat_worker import interrupt_expired_turn, lock_owner
from .database import database_factory
from .models import ChatTurn, now
from .runtime import ContainerRuntime, RuntimeFailure, RuntimeSettings, container_name, engine_environment


class RuntimeRecovery:
    def __init__(self, runtime, factory):
        self.runtime, self.factory = runtime, factory

    def engine(self, arguments, *, capture=False, timeout=10):
        try:
            return subprocess.run(
                [self.runtime.settings.executable, "--cgroup-manager=cgroupfs", *arguments],
                env=engine_environment(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=timeout,
                check=False,
                text=True,
            )
        except (OSError, subprocess.TimeoutExpired):
            raise RuntimeFailure("recovery_engine_unavailable") from None

    def snapshot(self, name, state):
        exists = self.engine(["container", "exists", name])
        if exists.returncode == 1:
            return None
        if exists.returncode != 0:
            raise RuntimeFailure("recovery_engine_unavailable")
        # Select only identity, status and mounts; never retrieve env, logs or arguments.
        template = '{"id":{{json .ID}},"status":{{json .State.Status}},"mounts":{{json .Mounts}}}'
        result = self.engine(["container", "inspect", "--format", template, name], capture=True)
        if result.returncode != 0:
            raise RuntimeFailure("recovery_inspection_changed")
        try:
            item = json.loads(result.stdout)
            if not re.fullmatch(r"[0-9a-f]{64}", item["id"]):
                raise ValueError
            mounts = [m for m in item["mounts"] if m.get("Destination") == "/state"]
            if len(mounts) != 1 or mounts[0].get("Type") != "bind":
                raise ValueError
            if Path(mounts[0]["Source"]).resolve() != state.resolve():
                raise ValueError
            if item["status"] not in {
                "configured",
                "created",
                "running",
                "paused",
                "stopped",
                "exited",
                "removing",
                "stopping",
            }:
                raise ValueError
        except (ValueError, KeyError, TypeError):
            raise RuntimeFailure("recovery_container_mismatch") from None
        return {"id": item["id"], "status": item["status"]}

    def inspect_or_recover(self, organization_id, owner_id, *, expected_container=None):
        organization_id, owner_id = str(UUID(organization_id)), str(UUID(owner_id))
        if (
            expected_container is not None
            and expected_container != "absent"
            and not re.fullmatch(r"[0-9a-f]{64}", expected_container)
        ):
            raise RuntimeFailure("recovery_confirmation_invalid")
        name = container_name(organization_id, owner_id)
        with self.factory.begin() as db:
            # A local operator is outside customer authorization. PostgreSQL row locks
            # coordinate this maintenance with workers, scheduler and API mutations.
            if db.get_bind().dialect.name != "postgresql":
                raise RuntimeFailure("recovery_requires_postgresql")
            db.execute(text("SET LOCAL lock_timeout = '5s'"))
            try:
                member = lock_owner(db, organization_id, owner_id)
            except OperationalError as error:
                if getattr(error.orig, "sqlstate", None) == "55P03":
                    raise RuntimeFailure("recovery_owner_busy") from None
                raise
            if member is None:
                raise RuntimeFailure("recovery_owner_not_found")
            turns = db.scalars(
                select(ChatTurn)
                .where(
                    ChatTurn.organization_id == organization_id,
                    ChatTurn.owner_id == owner_id,
                    ChatTurn.status.in_(("queued", "running")),
                )
                .order_by(ChatTurn.created_at, ChatTurn.id)
                .with_for_update()
            ).all()
            with self.runtime.owner_state(organization_id, owner_id) as state:
                container = self.snapshot(name, state)
                result = {
                    "organization_id": organization_id,
                    "owner_id": owner_id,
                    "observed_at": now(),
                    "container": container,
                    "pending_turns": [
                        {"id": t.id, "status": t.status, "lease_expires_at": t.lease_expires_at}
                        for t in turns
                    ],
                }
                if expected_container is None:
                    return result
                actual = container["id"] if container else "absent"
                if actual != expected_container:
                    raise RuntimeFailure("recovery_inspection_changed")
                if any(
                    t.status == "queued" or t.lease_expires_at is None or t.lease_expires_at > now()
                    for t in turns
                ):
                    raise RuntimeFailure("recovery_execution_pending")
                if container:
                    removed = self.engine(["rm", "--force", "--time", "5", container["id"]], timeout=20)
                    if removed.returncode != 0:
                        raise RuntimeFailure("recovery_removal_uncertain")
                    if self.snapshot(name, state) is not None:
                        raise RuntimeFailure("recovery_removal_uncertain")
                for turn in turns:
                    interrupt_expired_turn(db, turn)
                # Existing email/save receipts stay untouched: recovery cannot infer
                # whether Microsoft accepted an action or authorize another attempt.
                result.update(
                    recovery_id=str(uuid4()),
                    recovered_at=now(),
                    interrupted_turns=[t.id for t in turns],
                    status="recovered",
                )
                return result


def main():
    parser = argparse.ArgumentParser(description="AlpenData local runtime diagnosis and recovery")
    parser.add_argument("action", choices=("inspect", "recover"))
    parser.add_argument("--organization", required=True, type=UUID)
    parser.add_argument("--owner", required=True, type=UUID)
    parser.add_argument("--expected-container", help="Full inspected container ID, or 'absent'")
    args = parser.parse_args()
    if (args.action == "recover") != (args.expected_container is not None):
        parser.error("recover requires --expected-container; inspect must omit it")
    engine = None
    try:
        # No Microsoft, SMTP or model credentials are needed for recovery.
        settings = RuntimeSettings(
            Path(os.environ["ALPENDATA_RUNTIME_STATE_ROOT"]), os.environ["ALPENDATA_RUNTIME_IMAGE"]
        )
        engine, factory = database_factory(os.environ["ALPENDATA_DATABASE_URL"])
        recovery = RuntimeRecovery(ContainerRuntime(settings), factory)
        result = recovery.inspect_or_recover(
            str(args.organization), str(args.owner), expected_container=args.expected_container
        )
    except RuntimeFailure as error:
        uncertain = str(error) in {"recovery_engine_unavailable", "recovery_removal_uncertain"}
        print(json.dumps({"status": "uncertain" if uncertain else "refused", "error": str(error)}))
        return 1
    except (ValueError, KeyError):
        print(json.dumps({"status": "refused", "error": "recovery_configuration_invalid"}))
        return 1
    except SQLAlchemyError:
        print(json.dumps({"status": "uncertain", "error": "recovery_database_unavailable"}))
        return 1
    finally:
        if engine is not None:
            engine.dispose()
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
