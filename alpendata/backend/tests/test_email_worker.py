"""Real isolated Hermes prepares a review; only the owner's API confirmation sends."""

import json
import tempfile
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from model_http import completion, model_http
from test_documents import start_document_turn
from test_email_reviews import EmailHTTP, permit_email
from test_microsoft_connections import connected_service as connected_service
from test_sharepoint_documents import download_service as download_service

from alpendata_api.chat_worker import ChatWorker
from alpendata_api.model_gateway import ModelGateway
from alpendata_api.runtime import RuntimeSettings

pytestmark = pytest.mark.linux_only


def test_hermes_prepares_a_private_email_without_a_send_tool(download_service, request):
    image = request.config.getoption("--runtime-image")
    if not image or not request.config.getoption("--postgresql-bin"):
        pytest.skip("Requires real OCI image and PostgreSQL")
    app, client, settings, _, graph, org, alice, bob = download_service
    path = start_document_turn(download_service)
    http = EmailHTTP()
    graph.session = http
    message = {
        "to": ["client@example.com"],
        "subject": "Prochaine séance",
        "body": "Bonjour, préparons notre séance.",
    }

    def respond(body):
        names = {tool["function"]["name"] for tool in body.get("tools", [])}
        assert "alpendata_prepare_email" in names
        assert not any("send" in name for name in names)
        assert "synthetic-access-" not in json.dumps(body)
        answers = [item for item in body["messages"] if item["role"] == "tool"]
        if answers:
            prepared = json.loads(answers[-1]["content"])
            assert prepared["status"] == 200, prepared
            assert prepared["result"]["message"]["subject"] == message["subject"]
            assert prepared["result"]["attempts"] == []
            return 200, completion(body, content="Votre brouillon est prêt à relire dans le chat."), {}
        result = completion(body, content=None)
        result["choices"][0]["finish_reason"] = "tool_calls"
        result["choices"][0]["message"]["tool_calls"] = [
            {
                "id": uuid4().hex[:9],
                "type": "function",
                "function": {"name": "alpendata_prepare_email", "arguments": json.dumps(message)},
            }
        ]
        return 200, result, {}

    with (
        tempfile.TemporaryDirectory(prefix="alpendata-email-") as state,
        model_http(respond) as (transport, _, _),
    ):
        settings = replace(settings, runtime=RuntimeSettings(Path(state), image))
        worker = ChatWorker(
            settings, app.state.session_factory, gateway=ModelGateway(settings.model, session=transport)
        )
        assert worker.run_once()
        turn = client.get(path, headers=bob[2]).json()["turns"][0]
        assert turn["status"] == "completed", turn
        assert len(turn["emails"]) == 1 and not http.calls
        draft = turn["emails"][0]
        email_path = f"/api/organizations/{org}/emails/{draft['id']}"
        assert client.get(email_path, headers=alice[2]).status_code == 404
        permit_email(download_service)
        result = client.post(
            email_path + "/send", headers=bob[2], json={"version": draft["version"], "confirmed": True}
        )
        assert result.json()["attempts"][0]["status"] == "accepted", result.text
        assert len(http.calls) == 1
