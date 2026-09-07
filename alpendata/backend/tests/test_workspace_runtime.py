"""Real OCI parsers, per-conversation state and Hermes child agents."""

import base64
import json
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest
from test_runtime import completion

from alpendata_api.runtime import ContainerRuntime, RuntimeSettings

pytestmark = pytest.mark.linux_only


@pytest.fixture
def runtime(request):
    image = request.config.getoption("--runtime-image")
    if not image:
        pytest.skip("Requires a real runtime image")
    with tempfile.TemporaryDirectory(prefix="alpendata-workspace-runtime-") as directory:
        yield ContainerRuntime(RuntimeSettings(Path(directory), image))


def test_document_and_web_parsers_do_not_need_a_model_or_network(runtime):
    org, owner = str(uuid4()), str(uuid4())

    def reject(*_):
        pytest.fail("A pure parser requested a broker capability")

    text = "Source contract\n" + "A" * 14000
    result = runtime.run(
        org,
        owner,
        {
            "operation": "analyze_document",
            "state_scope": str(uuid4()),
            "filename": "contract.txt",
            "content_base64": base64.b64encode(text.encode()).decode(),
        },
        reject,
    )
    assert result["status"] == "ready" and result["partial"]
    assert result["pages"][0]["reference"].startswith("lines 1")
    assert "Source contract" in result["pages"][0]["text"]
    html = b"<h1>Independent evidence</h1><script>exfiltrate()</script><p>Verified &amp; cited</p>"
    result = runtime.run(
        org,
        owner,
        {
            "operation": "analyze_web",
            "state_scope": str(uuid4()),
            "media_type": "text/html",
            "content_base64": base64.b64encode(html).decode(),
        },
        reject,
    )
    assert "Verified & cited" in result["text"] and "exfiltrate" not in result["text"]


def test_native_hermes_delegation_returns_child_result_inside_same_scope(runtime):
    org, owner, conversation = (str(uuid4()) for _ in range(3))
    models, activity = [], []

    def broker(operation, body):
        if operation == "activity":
            activity.append(body)
            return {"status": 200, "body": {}}
        assert operation == "model"
        models.append(body)
        if body.get("_alpendata_background"):
            return completion(body, content="Child verified the meeting agenda.")
        if not any(message.get("role") == "tool" for message in body["messages"]):
            return completion(
                body,
                tool="alpendata_delegate",
                arguments={
                    "tasks": [
                        {
                            "goal": "Review the meeting agenda",
                            "context": "Agenda: goals, decisions and follow-up.",
                        }
                    ]
                },
            )
        return completion(body, content="Parent reviewed the delegated result.")

    result = runtime.run(
        org,
        owner,
        {
            "session_id": conversation,
            "state_scope": conversation,
            "model": "synthetic-model",
            "capabilities": [],
            "tool_revision": 7,
            "activity_enabled": True,
            "system_prompt": "You are AlpenData. Work only on this user's authorized task.",
            "message": "Review this agenda with one specialized worker.",
        },
        broker,
    )
    assert result.get("completed"), json.dumps(result)[:3000]
    assert any(body.get("_alpendata_background") for body in models), json.dumps(result)[:3000]
    answers = [message["content"] for message in result["messages"] if message.get("role") == "tool"]
    assert any("Child verified" in answer for answer in answers), answers
    assert any(item["label"].startswith("delegated_task_") for item in activity)
    assert (runtime.settings.state_root / "scoped" / org / owner / conversation).is_dir()
    assert not (runtime.settings.state_root / org / owner).exists()
