"""Real Hermes creates a file, publishes it over stdio, and serves a private download."""

import base64
import json
import shlex
import tempfile
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from model_http import completion, model_http
from test_documents import example_pdf, start_document_turn
from test_routines import connected_service as connected_service
from test_routines import routine_service as routine_service

from alpendata_api.chat_worker import ChatWorker
from alpendata_api.model_gateway import ModelGateway
from alpendata_api.runtime import RuntimeSettings

pytestmark = pytest.mark.linux_only


def test_hermes_publishes_private_documents_without_a_microsoft_connection(routine_service, request):
    image = request.config.getoption("--runtime-image")
    if not image or not request.config.getoption("--postgresql-bin"):
        pytest.skip("Requires real OCI image and PostgreSQL")
    app, client, settings, _, _, org, alice, bob = routine_service
    assert client.delete(f"/api/organizations/{org}/microsoft", headers=bob[2]).status_code == 204
    path = start_document_turn(routine_service)
    content = example_pdf()
    encoded = base64.b64encode(content).decode()
    program = (
        "from pathlib import Path; import base64, os; "
        f"Path('/state/workspace/session.pdf').write_bytes(base64.b64decode({encoded!r})); "
        "os.symlink('/etc/passwd', '/state/workspace/linked.pdf'); print('Created session.pdf')"
    )
    calls = [
        ("terminal", {"command": "python -c " + shlex.quote(program)}),
        ("alpendata_publish_document", {"path": "../.hermes/config.yaml"}),
        ("alpendata_publish_document", {"path": "linked.pdf"}),
        ("alpendata_publish_document", {"path": "session.pdf"}),
        ("alpendata_publish_document", {"path": "session.pdf"}),
    ]

    def respond(body):
        names = {tool["function"]["name"] for tool in body.get("tools", [])}
        assert "alpendata_publish_document" in names
        assert "alpendata_mail" not in names
        answers = [item for item in body["messages"] if item["role"] == "tool"]
        if len(answers) >= len(calls):
            assert json.loads(answers[1]["content"])["status"] == 400
            assert json.loads(answers[2]["content"])["status"] == 400
            saved = json.loads(answers[3]["content"])
            assert saved["status"] == 200, saved
            assert saved == json.loads(answers[4]["content"])
            return 200, completion(body, content="Your session document is ready."), {}
        tool, arguments = calls[len(answers)]
        answer = completion(body, content=None)
        answer["choices"][0]["finish_reason"] = "tool_calls"
        answer["choices"][0]["message"]["tool_calls"] = [
            {
                "id": uuid4().hex[:9],
                "type": "function",
                "function": {"name": tool, "arguments": json.dumps(arguments)},
            }
        ]
        return 200, answer, {}

    with (
        tempfile.TemporaryDirectory(prefix="alpendata-documents-") as state,
        model_http(respond) as (transport, _, _),
    ):
        settings = replace(settings, runtime=RuntimeSettings(Path(state), image))
        worker = ChatWorker(
            settings, app.state.session_factory, gateway=ModelGateway(settings.model, session=transport)
        )
        assert worker.run_once()
        detail = client.get(path, headers=bob[2]).json()
        turn = detail["turns"][0]
        assert turn["status"] == "completed", turn
        assert len(turn["artifacts"]) == 1
        download = f"/api/organizations/{org}/documents/{turn['artifacts'][0]['id']}/download"
        assert client.get(download, headers=bob[2]).content == content
        assert client.get(download, headers=alice[2]).status_code == 404
