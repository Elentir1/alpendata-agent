"""A real pipe exchange must not disable the host deadline while the provider is waiting."""

import subprocess
import sys
import time
from threading import Event

import pytest

from alpendata_api.runtime import ContainerRuntime, RuntimeFailure, RuntimeSettings

pytestmark = pytest.mark.linux_only


def test_broker_wait_does_not_extend_execution_deadline(tmp_path):
    entered, release, returned = Event(), Event(), Event()
    program = tmp_path / "waiting.py"
    program.write_text("""import json, sys, time, uuid
sys.stdin.readline()
print(json.dumps({"type":"request", "id":str(uuid.uuid4()), "operation":"model", "payload":{}}), flush=True)
time.sleep(60)
""")
    runtime = ContainerRuntime(RuntimeSettings(tmp_path / "state", "sha256:" + "0" * 64, timeout_seconds=10))

    def exchange(operation, body):
        entered.set()
        release.wait(30)
        returned.set()
        return {"status": 200, "body": {}}

    process = subprocess.Popen([sys.executable, str(program)], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    try:
        started = time.monotonic()
        with pytest.raises(RuntimeFailure, match="agent_timed_out"):
            runtime.communicate(process, {"purpose": "scheduled"}, exchange)
        assert entered.is_set() and not returned.is_set()
        assert 8 <= time.monotonic() - started < 15
    finally:
        release.set()
        assert returned.wait(5)
        process.kill()
        process.wait(timeout=5)
        process.stdin.close()
        process.stdout.close()
