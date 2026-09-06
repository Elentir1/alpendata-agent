"""The real Hermes tool chain dispatches only with frozen and current authority."""

import json
import tempfile
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from model_http import completion, model_http
from test_email_autonomy import enable_autonomy, queue_email
from test_email_reviews import EmailHTTP
from test_microsoft_connections import connected_service as connected_service
from test_sharepoint_documents import download_service as download_service

from alpendata_api.chat_worker import ChatWorker
from alpendata_api.connections import MicrosoftReader
from alpendata_api.model_gateway import ModelGateway
from alpendata_api.runtime import RuntimeSettings

pytestmark = pytest.mark.linux_only


def test_hermes_sends_through_the_personal_broker_after_explicit_autonomy(download_service, request):
    image = request.config.getoption("--runtime-image")
    if not image or not request.config.getoption("--postgresql-bin"):
        pytest.skip("Requires real OCI image and PostgreSQL")
    app, client, settings, provider, graph, org, alice, bob = download_service
    policy = enable_autonomy(download_service)
    path = queue_email(download_service)
    http = EmailHTTP()
    graph.session = http

    def respond(body):
        names = {tool["function"]["name"] for tool in body.get("tools", [])}
        assert {"alpendata_prepare_email", "alpendata_send_email"} <= names
        assert "synthetic-access-" not in json.dumps(body)
        answers = [json.loads(item["content"]) for item in body["messages"] if item["role"] == "tool"]
        if len(answers) == 2:
            assert answers[1]["status"] == 200, answers
            assert answers[1]["result"]["attempts"][-1]["status"] == "accepted"
            return 200, completion(body, content="Microsoft accepted the requested email."), {}
        name, arguments = (
            (
                "alpendata_prepare_email",
                {"to": ["client@example.com"], "subject": "Session", "body": "Our session is confirmed."},
            )
            if not answers
            else (
                "alpendata_send_email",
                {"draft_id": answers[0]["result"]["id"], "version": answers[0]["result"]["version"]},
            )
        )
        result = completion(body, content=None)
        result["choices"][0]["finish_reason"] = "tool_calls"
        result["choices"][0]["message"]["tool_calls"] = [
            {
                "id": uuid4().hex[:9],
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments)},
            }
        ]
        return 200, result, {}

    with (
        tempfile.TemporaryDirectory(prefix="alpendata-autonomy-") as state,
        model_http(respond) as (transport, _, _),
    ):
        settings = replace(settings, runtime=RuntimeSettings(Path(state), image))
        worker = ChatWorker(
            settings,
            app.state.session_factory,
            gateway=ModelGateway(settings.model, session=transport),
            microsoft=MicrosoftReader(settings, app.state.session_factory, provider, graph),
        )
        assert worker.run_once()
        turn = client.get(path, headers=bob[2]).json()["turns"][0]
        assert turn["status"] == "completed", turn
        receipt = turn["emails"][0]["attempts"][-1]
        assert receipt["status"] == "accepted" and receipt["initiator"] == "agent"
        assert receipt["autonomy_version"] == policy["version"]
        assert len(http.calls) == 1
        assert http.calls[0]["headers"]["Authorization"] == "Bearer synthetic-access-" + bob[1]
        assert client.get(path, headers=alice[2]).status_code == 404
