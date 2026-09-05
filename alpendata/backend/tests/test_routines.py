"""Proposal authorization and real broker evidence; external Microsoft responses are synthetic."""

import sys
from dataclasses import replace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_microsoft_connections import connected_service as connected_service
from test_microsoft_connections import start

from alpendata_api.app import create_app
from alpendata_api.chat_worker import ChatWorker
from alpendata_api.connections import MicrosoftReader
from alpendata_api.graph import GraphReader
from alpendata_api.microsoft_data import CALLBACK, MicrosoftData
from alpendata_api.model_gateway import ModelSettings
from alpendata_api.runtime import RuntimeSettings

PROPOSALS = [
    {
        "template": "mail_briefing",
        "title": "Client briefing",
        "benefit": "Prepare coaching follow-ups",
        "focus": "Client coaching requests",
    },
    {
        "template": "reply_preparation",
        "title": "Prepare a reply",
        "benefit": "Save writing time",
        "focus": "A client question",
    },
]


@pytest.fixture
def routine_service(connected_service, tmp_path):
    _, original, settings, microsoft, graph, org, alice, bob = connected_service
    microsoft.scopes = {"openid", "profile", "offline_access", "Mail.Read"}
    for person in (alice, bob):
        flow = start(original, microsoft, org, person, capabilities=("mail",))
        assert original.post(CALLBACK, data=flow, follow_redirects=False).status_code == 303
    settings = replace(
        settings,
        model=ModelSettings("mistral", "synthetic-model", "synthetic-key"),
        runtime=RuntimeSettings(tmp_path / "states", "sha256:" + "0" * 64, executable=sys.executable),
    )
    provider = MicrosoftData(settings, http_client=microsoft)
    reader = GraphReader(graph)
    app = create_app(settings, microsoft_provider=provider, graph=reader)
    with TestClient(app, base_url=settings.public_origin) as client:
        yield app, client, settings, provider, reader, org, alice, bob


def test_proposals_require_personal_profile_access_and_real_trial_evidence(routine_service):
    app, client, settings, provider, graph, org, alice, bob = routine_service
    base = f"/api/organizations/{org}"
    request = {"request_id": str(uuid4()), "language": "en", "refinement": "Help with my coaching clients"}
    assert (
        client.post(base + "/onboarding/proposals", headers=bob[2], json=request).json()["detail"]
        == "onboarding_required"
    )
    client.put(
        base + "/onboarding", headers=bob[2], json={"language": "en", "role": "Coach", "needs": "Follow-ups"}
    )
    result = client.post(base + "/onboarding/proposals", headers=bob[2], json=request)
    assert result.status_code == 202, result.text
    assert client.post(base + "/onboarding/proposals", headers=bob[2], json=request).json() == result.json()
    path = base + "/chat/conversations/" + result.json()["conversation"]["id"]
    assert client.get(path, headers=alice[2]).status_code == 404
    # Queue and broker contract only here; the OCI integration is tested separately.
    worker = ChatWorker(
        settings,
        app.state.session_factory,
        runtime=object(),
        microsoft=MicrosoftReader(settings, app.state.session_factory, provider, graph),
    )
    job = worker.claim()
    invalid = {
        "kind": "routine_proposals",
        "proposals": [PROPOSALS[0], {**PROPOSALS[1], "template": "meeting_preparation"}],
    }
    assert worker.tool(job, ["mail"], invalid)["status"] == 409
    assert client.get(path, headers=bob[2]).json()["proposals"] == []
    payload = {"kind": "routine_proposals", "proposals": PROPOSALS}
    assert worker.tool(job, ["mail"], {**payload, "owner_id": alice[0]})["status"] == 400
    saved = worker.tool(job, ["mail"], payload)
    assert saved["status"] == 200
    assert worker.tool(job, ["mail"], payload)["body"]["proposals"] == saved["body"]["proposals"]
    worker.finish(job, result={"response": "Choose your first task"})
    proposal = client.get(path, headers=bob[2]).json()["proposals"][0]
    trial_path = base + "/routines/" + proposal["id"] + "/trial"
    intent = {"request_id": str(uuid4())}
    assert client.post(trial_path, headers=alice[2], json=intent).status_code == 404
    trial = client.post(trial_path, headers=bob[2], json=intent).json()
    assert client.post(trial_path, headers=bob[2], json=intent).json() == trial
    trial_chat = base + "/chat/conversations/" + trial["conversation_id"]
    job = worker.claim()
    assert worker.tool(job, ["mail"], payload)["status"] == 403
    worker.finish(job, result={"response": "I consulted all sources (unsupported model claim)"})
    assert client.get(trial_chat, headers=bob[2]).json()["trials"][0]["sources_verified"] is False
    trial = client.post(trial_path, headers=bob[2], json={"request_id": str(uuid4())}).json()
    job = worker.claim()
    assert (
        worker.tool(job, ["mail"], {"capability": "files", "arguments": {"query": "coach"}})["status"] == 403
    )
    assert worker.tool(job, ["mail"], {"capability": "mail", "arguments": {}})["status"] == 200
    worker.finish(job, result={"response": "Briefing from the actual broker read"})
    detail = client.get(base + "/chat/conversations/" + trial["conversation_id"], headers=bob[2]).json()
    assert detail["trials"][0]["sources_verified"] is True
    assert detail["turns"][0]["sources"][0]["label"] == "synthetic-access-" + bob[1]
    assert (
        client.get(base + "/chat/conversations/" + trial["conversation_id"], headers=alice[2]).status_code
        == 404
    )
    no_tools = client.post(
        base + "/onboarding/proposals", headers=bob[2], json={**request, "request_id": str(uuid4())}
    ).json()
    job = worker.claim()
    worker.finish(job, result={"response": "I have prepared your tasks without saving proposals"})
    missing = client.get(
        base + "/chat/conversations/" + no_tools["conversation"]["id"], headers=bob[2]
    ).json()
    assert missing["turns"][0]["error_code"] == "routine_proposals_missing"
    assert missing["turns"][0]["response"] is None
    assert client.delete(base + "/microsoft", headers=bob[2]).status_code == 204
    assert (
        client.post(trial_path, headers=bob[2], json={"request_id": str(uuid4())}).json()["detail"]
        == "microsoft_reconnect_required"
    )
