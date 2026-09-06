"""Real API, PostgreSQL, MSAL, model HTTP and OCI worker; external replies are synthetic."""

import json
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Event
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from model_http import completion, model_http
from sqlalchemy import select
from test_microsoft_connections import connected_service as connected_service
from test_microsoft_connections import start

from alpendata_api.app import create_app
from alpendata_api.chat_worker import ChatWorker
from alpendata_api.connections import MicrosoftReader
from alpendata_api.graph import GraphReader
from alpendata_api.microsoft_data import CALLBACK, MicrosoftData
from alpendata_api.model_gateway import ModelGateway, ModelSettings
from alpendata_api.models import ChatTurn, ModelCall
from alpendata_api.runtime import RuntimeSettings

pytestmark = pytest.mark.linux_only


def test_chat_runs_with_own_microsoft_access_resumes_and_cancels(connected_service, request):
    image = request.config.getoption("--runtime-image")
    if not image or not request.config.getoption("--postgresql-bin"):
        pytest.skip("Requires a real image and PostgreSQL")
    _, original, settings, microsoft_http, graph_http, org, alice, bob = connected_service
    microsoft_http.scopes = {"openid", "profile", "offline_access", "Mail.Read"}
    for account in (alice, bob):
        flow = start(original, microsoft_http, org, account, capabilities=("mail",))
        assert original.post(CALLBACK, data=flow, follow_redirects=False).status_code == 303
    original.put(
        f"/api/organizations/{org}/onboarding",
        headers=bob[2],
        json={"language": "en", "role": "Coach", "needs": "Briefing"},
    )
    entered, release = Event(), Event()
    prefixes = []

    def provider(body):
        if not body.get("tools"):
            return 200, completion(body, content='{"title":"Personal briefing"}'), {}
        prefixes.append(body["messages"][0])
        messages = body["messages"]
        latest = max(index for index, item in enumerate(messages) if item["role"] == "user")
        current = messages[latest:]
        if current[0]["content"] == "Cancel this turn":
            entered.set()
            assert release.wait(30)
            return 200, completion(body, content="This cancelled answer must not be delivered"), {}
        if not any(item["role"] == "tool" for item in current):
            data = completion(body, content=None)
            data["choices"][0]["finish_reason"] = "tool_calls"
            data["choices"][0]["message"]["tool_calls"] = [
                {
                    "id": uuid4().hex[:9],
                    "type": "function",
                    "function": {"name": "alpendata_mail", "arguments": "{}"},
                }
            ]
            return 200, data, {}
        if "microsoft_reconnect_required" in json.dumps(current):
            return 200, completion(body, content="Please reconnect your mailbox"), {}
        assert "synthetic-access-" + bob[1] in json.dumps(current)
        assert "synthetic-access-" + alice[1] not in json.dumps(body)
        return 200, completion(body, content="Bob's private briefing"), {}

    with (
        tempfile.TemporaryDirectory(prefix="alpendata-chat-") as temporary,
        model_http(provider) as (
            transport,
            received,
            _,
        ),
    ):
        settings = replace(
            settings,
            model=ModelSettings("mistral", "synthetic-model", "synthetic-server-key"),
            runtime=RuntimeSettings(Path(temporary), image),
        )
        provider_ms = MicrosoftData(settings, http_client=microsoft_http)
        graph = GraphReader(graph_http)
        app = create_app(settings, microsoft_provider=provider_ms, graph=graph)
        base = f"/api/organizations/{org}"
        with TestClient(app, base_url=settings.public_origin) as client:
            identifier = client.post(
                base + "/chat/conversations", headers=bob[2], json={"language": "en"}
            ).json()["id"]
            path = base + "/chat/conversations/" + identifier
            first = client.post(
                path + "/turns",
                headers=bob[2],
                json={"request_id": str(uuid4()), "message": "Prepare Bob's briefing"},
            ).json()
            assert first["status"] == "queued"
        # Replace the API process before execution: the queue and history are durable.
        app = create_app(settings, microsoft_provider=provider_ms, graph=graph)
        with TestClient(app, base_url=settings.public_origin) as client:
            factory = app.state.session_factory
            worker = ChatWorker(
                settings,
                factory,
                gateway=ModelGateway(settings.model, session=transport),
                microsoft=MicrosoftReader(settings, factory, provider_ms, graph),
            )
            assert worker.run_once()
            data = client.get(path, headers=bob[2]).json()
            assert data["turns"][0]["status"] == "completed", data
            assert data["turns"][0]["response"] == "Bob's private briefing"
            assert client.get(path, headers=alice[2]).status_code == 404
            assert len(graph_http.calls) == 1
            assert graph_http.calls[0][2]["headers"]["Authorization"] == "Bearer synthetic-access-" + bob[1]
            with factory() as db:
                calls = db.scalars(select(ModelCall).where(ModelCall.turn_id == first["id"])).all()
                assert len(calls) == len(received) and calls
                assert all(call["body"].get("tools") for call in received)
                assert all(call.status == "completed" and call.total_tokens == 120 for call in calls)
                assert {call.owner_id for call in calls} == {bob[0]}
            assert client.delete(base + "/microsoft", headers=bob[2]).status_code == 204
            client.post(
                path + "/turns",
                headers=bob[2],
                json={"request_id": str(uuid4()), "message": "Refresh the briefing"},
            )
            assert worker.run_once()
            resumed = client.get(path, headers=bob[2]).json()
            assert resumed["turns"][-1]["response"] == "Please reconnect your mailbox", resumed
            assert all(prefix == prefixes[0] for prefix in prefixes)
            assert len(graph_http.calls) == 1
            assert any(
                "Bob's private briefing" in json.dumps(call["body"]["messages"])
                for call in received
                if call["body"].get("tools")
            )
            third = client.post(
                path + "/turns",
                headers=bob[2],
                json={"request_id": str(uuid4()), "message": "Cancel this turn"},
            ).json()
            with ThreadPoolExecutor(max_workers=1) as pool:
                running = pool.submit(worker.run_once)
                try:
                    assert entered.wait(30)
                    cancel = client.post(path + "/turns/" + third["id"] + "/cancel", headers=bob[2])
                    assert cancel.json()["cancel_requested"]
                finally:
                    release.set()
                assert running.result(timeout=45)
            cancelled = client.get(path, headers=bob[2]).json()["turns"][-1]
            assert cancelled["status"] == "cancelled" and cancelled["response"] is None
            with factory() as db:
                receipt = db.scalar(select(ModelCall).where(ModelCall.turn_id == third["id"]))
                assert receipt.status == "completed" and receipt.total_tokens == 120
            final = client.post(
                path + "/turns", headers=bob[2], json={"request_id": str(uuid4()), "message": "Pending task"}
            ).json()
            client.patch(
                base + "/members/" + bob[0],
                headers=alice[2],
                json={"version": 1, "active": False, "licensed": True, "role": "member"},
            )
            before = len(received)
            assert worker.run_once()
            assert len(received) == before and client.get(path, headers=bob[2]).status_code == 404
            with factory() as db:
                revoked = db.get(ChatTurn, final["id"])
                assert revoked.status == "failed" and revoked.error_code == "agent_access_revoked"
            assert worker.run_once() is False
