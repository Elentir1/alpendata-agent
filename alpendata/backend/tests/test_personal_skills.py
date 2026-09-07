"""Exercise real Hermes skills/todos, process resumption and separate owner mounts."""

import json
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest
from test_runtime import completion

from alpendata_api.runtime import ContainerRuntime, RuntimeSettings

pytestmark = pytest.mark.linux_only


def test_personal_skills_persist_without_changing_conversation_prefix_or_peer_state(request):
    image = request.config.getoption("--runtime-image")
    if not image:
        pytest.skip("Requires a real OCI image")
    with tempfile.TemporaryDirectory(prefix="alpendata-skills-") as temporary:
        runtime = ContainerRuntime(RuntimeSettings(Path(temporary), image))
        org, alice, bob = (str(uuid4()) for _ in range(3))
        marker = "PRIVATE-PROCEDURE-" + uuid4().hex
        skill = (
            "---\nname: client-briefing\ndescription: Use when preparing a client briefing.\n---\n"
            "# Client briefing\n\n## Steps\n1. Ask for the meeting goal.\n2. Summarize next steps.\n"
            "\n## Quality check\nConfirm the meeting goal is present.\n\n" + marker
        )
        calls = []
        steps = [
            (
                "todo_list",
                {"todos": [{"id": "brief", "content": "Save briefing workflow", "status": "in_progress"}]},
            ),
            (
                "skill_manage",
                {"operations": [{"action": "create", "name": "client-briefing", "content": skill}]},
            ),
            ("skill_view", {"name": "client-briefing"}),
            (
                "todo_list",
                {"todos": [{"id": "brief", "content": "Save briefing workflow", "status": "completed"}]},
            ),
        ]

        def create(operation, body):
            assert operation == "model"
            calls.append(body)
            names = {item["function"]["name"] for item in body["tools"]}
            assert {"skills_list", "skill_view", "skill_manage", "todo_list"} <= names
            assert not {"delegate_task", "browser_navigate", "web_search"} & names
            if len(calls) <= len(steps):
                tool, arguments = steps[len(calls) - 1]
                return completion(body, tool=tool, arguments=arguments)
            return completion(body, content="Workflow saved")

        payload = {
            "session_id": str(uuid4()),
            "model": "synthetic-model",
            "capabilities": [],
            "tool_revision": 6,
            "system_prompt": "You are AlpenData.",
            "message": "Save my workflow",
        }
        result = runtime.run(org, alice, payload, create)
        assert result["completed"] and not result["failed"]
        stored = Path(temporary) / org / alice / ".hermes/skills/client-briefing/SKILL.md"
        assert marker in stored.read_text()
        results = [item for item in result["messages"] if item["role"] == "tool"]
        assert marker in results[2]["content"]
        assert json.loads(results[-1]["content"])["todos"][0]["status"] == "completed"

        def resume(operation, body):
            assert operation == "model"
            assert body["messages"][0] == calls[0]["messages"][0]
            assert body["tools"] == calls[0]["tools"]
            assert marker in json.dumps(body["messages"])
            return completion(body, content="Continuing")

        assert runtime.run(org, alice, {**payload, "message": "Continue"}, resume)["completed"]
        inspected = []

        def inspect(operation, body):
            assert operation == "model"
            inspected.append(body)
            latest = max(i for i, item in enumerate(body["messages"]) if item["role"] == "user")
            if not any(item["role"] == "tool" for item in body["messages"][latest:]):
                return completion(body, tool="skills_list", arguments={})
            return completion(body, content="Skills inspected")

        fresh = {**payload, "session_id": str(uuid4()), "message": "List saved workflows"}
        own = runtime.run(org, alice, fresh, inspect)
        assert "client-briefing" in json.dumps(own["messages"])
        inspected.clear()
        peer = runtime.run(org, bob, {**fresh, "session_id": str(uuid4())}, inspect)
        assert "client-briefing" not in json.dumps(peer["messages"])
        assert marker not in json.dumps(inspected)

        def legacy(operation, body):
            assert operation == "model"
            names = {item["function"]["name"] for item in body["tools"]}
            assert not {"skills_list", "skill_manage", "todo_list"} & names
            return completion(body, content="Legacy tools retained")

        assert runtime.run(org, bob, {**fresh, "session_id": str(uuid4()), "tool_revision": 5}, legacy)[
            "completed"
        ]
        assert runtime.run(org, bob, {**fresh, "session_id": str(uuid4()), "purpose": "scheduled"}, legacy)[
            "completed"
        ]
