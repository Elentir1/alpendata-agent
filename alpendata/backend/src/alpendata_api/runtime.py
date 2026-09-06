"""Rootless OCI execution. Container output is untrusted broker input.

Only the caller's server-verified owner selects the state mount. The container
receives no host credentials, network, sibling volumes or administrative socket.
"""

import hashlib
import json
import os
import selectors
import subprocess
import sys
import threading
import time
from concurrent.futures import Future
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

FRAME_LIMIT = 8 * 1024 * 1024


class RuntimeFailure(Exception):
    pass


def container_name(organization_id, owner_id):
    owner_key = f"{UUID(organization_id)}:{UUID(owner_id)}"
    return "alpendata-" + hashlib.sha256(owner_key.encode()).hexdigest()[:48]


def engine_environment():
    # Service credentials and engine overrides must not reach the subprocess.
    return {key: os.environ[key] for key in ("PATH", "HOME", "XDG_RUNTIME_DIR") if key in os.environ}


def frame(value):
    encoded = json.dumps(value, ensure_ascii=True, allow_nan=False).encode() + b"\n"
    if len(encoded) > FRAME_LIMIT:
        raise RuntimeFailure("agent_message_too_large")
    return encoded


@dataclass(frozen=True)
class RuntimeSettings:
    state_root: Path
    image: str
    executable: str = "/usr/bin/podman"
    timeout_seconds: int = 300

    def __post_init__(self):
        if not self.state_root.is_absolute() or not Path(self.executable).is_absolute():
            raise ValueError("Runtime paths must be absolute")
        if not self.image.startswith("sha256:") or len(self.image) != 71:
            raise ValueError("Runtime image must be pinned to a local image ID")
        int(self.image[7:], 16)
        if not 10 <= self.timeout_seconds <= 900:
            raise ValueError("Runtime timeout must be between 10 and 900 seconds")


class ContainerRuntime:
    def __init__(self, settings: RuntimeSettings):
        if sys.platform != "linux":
            raise RuntimeFailure("agent_requires_linux")
        self.settings = settings

    @contextmanager
    def owner_state(self, organization_id, owner_id):
        import fcntl

        organization_id, owner_id = str(UUID(organization_id)), str(UUID(owner_id))
        root = self.settings.state_root.resolve()
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        locks = root / "locks"
        locks.mkdir(mode=0o700, exist_ok=True)
        with (locks / f"{organization_id}-{owner_id}.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeFailure("agent_already_running") from None
            try:
                parent = root / organization_id
                parent.mkdir(mode=0o700, exist_ok=True)
                state = parent / owner_id
                state.mkdir(mode=0o700, exist_ok=True)
                if state.is_symlink() or parent.is_symlink() or not state.resolve().is_relative_to(root):
                    raise RuntimeFailure("agent_state_invalid")
                yield state
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def command(self, name, state):
        return [
            self.settings.executable,
            "--cgroup-manager=cgroupfs",
            "run",
            "--rm",
            "--interactive",
            "--pull=never",
            "--name",
            name,
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--userns=keep-id:uid=1000,gid=1000",
            "--user=1000:1000",
            "--pids-limit=128",
            "--memory=1g",
            "--cpus=1",
            "--ulimit=nofile=1024:1024",
            "--tmpfs=/tmp:rw,nosuid,nodev,size=128m,mode=1777",
            "--volume",
            f"{state}:/state:rw",
            self.settings.image,
        ]

    def run(self, organization_id, owner_id, payload, exchange, *, check=None):
        """Exchange is bound by the caller to one authorized execution, never its payload."""
        with self.owner_state(organization_id, owner_id) as state:
            name = container_name(organization_id, owner_id)
            # An allowlist prevents service secrets and container-engine overrides
            # from propagating through the controller's process environment.
            environment = engine_environment()
            existing = subprocess.run(
                [self.settings.executable, "--cgroup-manager=cgroupfs", "container", "exists", name],
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
                check=False,
            )
            if existing.returncode == 0:
                # A crashed supervisor may have left a container. Do not start a
                # second writer or silently delete an execution of uncertain state.
                raise RuntimeFailure("agent_recovery_required")
            if existing.returncode != 1:
                raise RuntimeFailure("agent_runtime_unavailable")
            process = subprocess.Popen(
                self.command(name, state),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env=environment,
                start_new_session=True,
            )
            try:
                result = self.communicate(process, payload, exchange, check=check)
                try:
                    code = process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    raise RuntimeFailure("agent_shutdown_failed") from None
                if code != 0:
                    raise RuntimeFailure("agent_execution_failed")
                return result
            finally:
                if process.poll() is None:
                    # Remove this exact generated container, including descendants;
                    # killing only the attached CLI could leave the agent running.
                    try:
                        subprocess.run(
                            [self.settings.executable, "--cgroup-manager=cgroupfs", "rm", "--force", name],
                            env=environment,
                            stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            timeout=20,
                            check=False,
                        )
                    finally:
                        if process.poll() is None:
                            process.kill()
                        process.wait(timeout=10)
                for stream in (process.stdin, process.stdout):
                    stream.close()

    def communicate(self, process, payload, exchange, *, check=None):
        budget = (
            min(self.settings.timeout_seconds, 180)
            if payload.get("purpose") == "scheduled"
            else self.settings.timeout_seconds
        )
        deadline = time.monotonic() + budget
        output, pending = bytearray(), bytearray(frame(payload))
        used = set()
        in_flight = None

        def broker_reply(future, operation, body):
            try:
                future.set_result(exchange(operation, body))
            except Exception as error:
                future.set_exception(error)

        with selectors.DefaultSelector() as selector:
            os.set_blocking(process.stdout.fileno(), False)
            os.set_blocking(process.stdin.fileno(), False)
            selector.register(process.stdout, selectors.EVENT_READ)
            selector.register(process.stdin, selectors.EVENT_WRITE)
            while True:
                if check is not None:
                    check()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RuntimeFailure("agent_timed_out")
                if in_flight is not None and in_flight[1].done():
                    identifier, future = in_flight
                    pending.extend(frame({"type": "response", "id": identifier, **future.result()}))
                    in_flight = None
                    selector.register(process.stdin, selectors.EVENT_WRITE)
                events = selector.select(min(remaining, 1))
                for key, _ in events:
                    if key.fileobj is process.stdin:
                        try:
                            count = os.write(process.stdin.fileno(), pending)
                        except BlockingIOError:
                            continue
                        except BrokenPipeError:
                            raise RuntimeFailure("agent_execution_failed") from None
                        del pending[:count]
                        if not pending:
                            selector.unregister(process.stdin)
                        continue
                    chunk = os.read(process.stdout.fileno(), 65536)
                    if not chunk:
                        raise RuntimeFailure("agent_execution_failed")
                    output.extend(chunk)
                    if len(output) > FRAME_LIMIT:
                        raise RuntimeFailure("agent_message_too_large")
                    while b"\n" in output:
                        line, _, rest = output.partition(b"\n")
                        output = bytearray(rest)
                        try:
                            message = json.loads(line)
                            if not isinstance(message, dict):
                                raise ValueError()
                            kind = message.get("type")
                            if kind == "error" and message.get("code") == "agent_execution_failed":
                                raise RuntimeFailure("agent_execution_failed")
                            if kind == "result":
                                if (
                                    pending
                                    or in_flight is not None
                                    or not isinstance(message.get("response"), str)
                                    or not isinstance(message.get("messages"), list)
                                ):
                                    raise ValueError()
                                return message
                            if kind != "request" or pending or in_flight is not None or len(used) >= 80:
                                raise ValueError()
                            identifier = str(UUID(message["id"]))
                            if (
                                identifier in used
                                or message["operation"] not in {"model", "tool"}
                                or not isinstance(message["payload"], dict)
                            ):
                                raise ValueError()
                            used.add(identifier)
                        except (ValueError, TypeError, KeyError):
                            raise RuntimeFailure("agent_protocol_invalid") from None
                        future = Future()
                        in_flight = (identifier, future)
                        # Accepted calls may return late; their receipts remain tied
                        # to this job while the controller enforces its deadline.
                        threading.Thread(
                            target=broker_reply,
                            args=(future, message["operation"], message["payload"]),
                            name="alpendata-broker-reply",
                            daemon=True,
                        ).start()
