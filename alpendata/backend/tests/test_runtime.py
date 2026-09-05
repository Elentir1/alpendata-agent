"""Real OCI containers and Hermes tools; only the remote model/broker data is synthetic."""

import json
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from alpendata_api.runtime import ContainerRuntime, RuntimeFailure, RuntimeSettings

pytestmark = pytest.mark.linux_only


def test_broker_rejects_unrecognized_operations_before_dispatch(tmp_path):
    runtime = ContainerRuntime(RuntimeSettings(tmp_path, "sha256:" + "0" * 64))
    emitted = {
        "type": "request",
        "id": str(uuid4()),
        "operation": "administrator",
        "payload": {"owner_id": str(uuid4())},
    }
    program = "import sys; sys.stdin.readline(); print(" + repr(json.dumps(emitted)) + ", flush=True)"
    child = subprocess.Popen([sys.executable, "-c", program], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    calls = []
    try:
        with pytest.raises(RuntimeFailure, match="agent_protocol_invalid"):
            runtime.communicate(child, {"message": "Hello"}, lambda *args: calls.append(args))
        assert not calls
    finally:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=10)
        child.stdin.close()
        child.stdout.close()


def completion(body, *, content=None, tool=None, arguments=None):
    message = {"role": "assistant", "content": content}
    if tool:
        message["tool_calls"] = [
            {
                "id": "call_" + uuid4().hex,
                "type": "function",
                "function": {"name": tool, "arguments": json.dumps(arguments)},
            }
        ]
    return {
        "status": 200,
        "body": {
            "id": "synthetic_completion",
            "object": "chat.completion",
            "created": 1,
            "model": body["model"],
            "choices": [{"index": 0, "message": message, "finish_reason": "tool_calls" if tool else "stop"}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
        },
    }


def test_hermes_turn_tools_private_memory_and_network_isolation(request):
    image = request.config.getoption("--runtime-image")
    if not image:
        pytest.skip("Use --runtime-image to exercise real containers")
    with tempfile.TemporaryDirectory(prefix="alpendata-runtime-") as temporary:
        root = Path(temporary)
        runtime = ContainerRuntime(RuntimeSettings(root / "states", image))
        org, alice, bob = (str(uuid4()) for _ in range(3))
        with runtime.owner_state(org, alice):
            with pytest.raises(RuntimeFailure, match="agent_already_running"):
                with runtime.owner_state(org, alice):
                    pytest.fail("Concurrent state access was admitted")
        secret = "SYNTHETIC-PRIVATE-" + uuid4().hex
        host_file = root / "host-private.txt"
        host_file.write_text(secret)
        with runtime.owner_state(org, bob) as other:
            (other / "colleague.txt").write_text(secret)
            peer_file = other / "colleague.txt"
        probe = """import os, json, socket
from pathlib import Path
result = {'uid': os.getuid(), 'host_readable': Path(HOST).exists(), 'peer_readable': Path(PEER).exists(),
    'socket_visible': Path('/var/run/docker.sock').exists(), 'home': os.environ.get('HERMES_HOME')}
try:
    socket.create_connection(('1.1.1.1',443), timeout=1).close()
    result['external_network'] = True
except OSError:
    result['external_network'] = False
print(json.dumps(result))
""".replace("HOST", repr(str(host_file))).replace("PEER", repr(str(peer_file)))
        model_calls, tool_calls = [], []

        def exchange(operation, body):
            if operation == "tool":
                tool_calls.append(body)
                assert body == {"capability": "mail", "arguments": {}}
                return {"status": 200, "body": {"messages": [{"subject": "Synthetic client briefing"}]}}
            if not body.get("tools"):
                return completion(body, content='{"title": "Synthetic conversation"}')
            model_calls.append(body)
            assert "You are AlpenData" in body["messages"][0]["content"]
            assert not body.get("stream")
            schemas = {item["function"]["name"] for item in body.get("tools", [])}
            assert {"memory", "terminal", "alpendata_mail"} <= schemas
            assert "alpendata_files" not in schemas
            answers = [
                (
                    "memory",
                    {"action": "add", "target": "user", "content": "Prefers French for client briefings."},
                ),
                ("terminal", {"command": "python -c " + shlex.quote(probe)}),
                ("alpendata_mail", {}),
            ]
            if len(model_calls) <= len(answers):
                tool, arguments = answers[len(model_calls) - 1]
                return completion(body, tool=tool, arguments=arguments)
            return completion(body, content="Synthetic verified briefing")

        payload = {
            "session_id": str(uuid4()),
            "model": "synthetic-model",
            "capabilities": ["mail"],
            "system_prompt": "You are AlpenData. Help the user with their work.",
            "message": "Remember my preferred language and prepare a briefing.",
            "history": None,
        }
        result = runtime.run(org, alice, payload, exchange)
        assert result["completed"] and not result["failed"]
        assert result["response"] == "Synthetic verified briefing"
        assert len(tool_calls) == 1
        tool_results = [entry for entry in result["messages"] if entry["role"] == "tool"]
        terminal = json.loads(tool_results[1]["content"])
        observed = json.loads(terminal["output"].strip())
        assert observed == {
            "uid": 1000,
            "host_readable": False,
            "peer_readable": False,
            "socket_visible": False,
            "home": "/state/.hermes",
            "external_network": False,
        }
        assert secret not in json.dumps(result)
        alice_memory = root / "states" / org / alice / ".hermes" / "memories" / "USER.md"
        assert "Prefers French" in alice_memory.read_text()
        assert not (root / "states" / org / bob / ".hermes").exists()
        # Resumption must keep the same conversation prefix across fresh processes.
        resumed = []

        def resume_exchange(operation, body):
            assert operation == "model"
            if not body.get("tools"):
                return completion(body, content='{"title": "Synthetic conversation"}')
            resumed.append(body)
            assert body["messages"][0] == model_calls[0]["messages"][0]
            assert any(item.get("content") == result["response"] for item in body["messages"])
            return completion(body, content="Continued briefing")

        again = {**payload, "message": "Continue", "history": result["messages"]}
        assert runtime.run(org, alice, again, resume_exchange)["response"] == "Continued briefing"
        assert resumed
        # A fresh container for another user starts with no peer memory.
        seen = []

        def other_exchange(operation, body):
            assert operation == "model"
            assert "Prefers French" not in json.dumps(body)
            if not body.get("tools"):
                return completion(body, content='{"title": "Synthetic conversation"}')
            seen.append(body)
            return completion(body, content="Another workspace")

        other_payload = {**payload, "session_id": str(uuid4()), "message": "Hello", "capabilities": []}
        assert runtime.run(org, bob, other_payload, other_exchange)["response"] == "Another workspace"
        assert seen
