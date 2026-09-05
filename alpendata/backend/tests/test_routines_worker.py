"""Hermes generates real proposal tool calls and runs a trial in separate OCI containers."""

import json
import tempfile
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from model_http import completion, model_http
from test_routines import PROPOSALS
from test_routines import connected_service as connected_service
from test_routines import routine_service as routine_service

from alpendata_api.chat_worker import ChatWorker
from alpendata_api.connections import MicrosoftReader
from alpendata_api.model_gateway import ModelGateway
from alpendata_api.models import RoutineSchedule, now
from alpendata_api.runtime import RuntimeSettings
from alpendata_api.schedule_worker import ScheduleWorker

pytestmark = pytest.mark.linux_only


def test_hermes_onboarding_and_trial_use_actual_registered_tools(routine_service, request):
    image = request.config.getoption("--runtime-image")
    if not image or not request.config.getoption("--postgresql-bin"):
        pytest.skip("Requires real OCI image and PostgreSQL")
    app, client, settings, provider, graph, org, alice, bob = routine_service
    base = f"/api/organizations/{org}"
    client.put(
        base + "/onboarding",
        headers=bob[2],
        json={"language": "en", "role": "Coach", "needs": "Client follow-ups"},
    )
    planning = client.post(
        base + "/onboarding/proposals",
        headers=bob[2],
        json={
            "request_id": str(uuid4()),
            "language": "en",
            "refinement": "Prepare client coaching follow-ups",
        },
    ).json()

    def respond(body):
        names = {item["function"]["name"] for item in body.get("tools", [])}
        planning = "alpendata_propose_routines" in names
        assert "alpendata_mail" in names and "alpendata_files" not in names
        if any(item.get("content") == "Execute the scheduled task once." for item in body["messages"]):
            assert "memory" not in names
        if any(item["role"] == "tool" for item in body["messages"]):
            if not planning:
                assert "synthetic-access-" + bob[1] in json.dumps(body)
                assert "synthetic-access-" + alice[1] not in json.dumps(body)
            return 200, completion(body, content="Choose a task" if planning else "Your client briefing"), {}
        answer = completion(body, content=None)
        answer["choices"][0]["finish_reason"] = "tool_calls"
        answer["choices"][0]["message"]["tool_calls"] = [
            {
                "id": uuid4().hex[:9],
                "type": "function",
                "function": {
                    "name": "alpendata_propose_routines" if planning else "alpendata_mail",
                    "arguments": json.dumps({"proposals": PROPOSALS} if planning else {}),
                },
            }
        ]
        return 200, answer, {}

    with (
        tempfile.TemporaryDirectory(prefix="alpendata-routines-") as state,
        model_http(respond) as (transport, received, _),
    ):
        settings = replace(settings, runtime=RuntimeSettings(Path(state), image))
        worker = ChatWorker(
            settings,
            app.state.session_factory,
            gateway=ModelGateway(settings.model, session=transport),
            microsoft=MicrosoftReader(settings, app.state.session_factory, provider, graph),
        )
        assert worker.run_once()
        detail = client.get(
            base + "/chat/conversations/" + planning["conversation"]["id"], headers=bob[2]
        ).json()
        assert detail["turns"][0]["status"] == "completed", detail
        assert len(detail["proposals"]) == len(PROPOSALS)
        assert detail["trials"] == []
        trial = client.post(
            base + "/routines/" + detail["proposals"][0]["id"] + "/trial",
            headers=bob[2],
            json={"request_id": str(uuid4())},
        ).json()
        assert worker.run_once()
        result = client.get(base + "/chat/conversations/" + trial["conversation_id"], headers=bob[2]).json()
        assert result["turns"][0]["status"] == "completed", result
        assert result["trials"][0]["sources_verified"] is True
        assert result["turns"][0]["sources"]
        assert len(received) == 4
        scheduled = client.post(
            base + "/schedules",
            headers=bob[2],
            json={
                "request_id": str(uuid4()),
                "reviewed_trial_id": trial["id"],
                "reviewed": True,
                "frequency": "daily",
                "local_time": "09:00",
                "timezone": "Europe/Zurich",
            },
        ).json()
        with app.state.session_factory.begin() as db:
            db.get(RoutineSchedule, scheduled["id"]).next_run_at = now() - 1
        assert ScheduleWorker(settings, app.state.session_factory).tick() == 1
        assert worker.run_once()
        runs = client.get(base + "/schedules/" + scheduled["id"] + "/occurrences", headers=bob[2]).json()
        assert runs["occurrences"][0]["status"] == "completed", runs
        scheduled_result = client.get(
            base + "/chat/conversations/" + runs["occurrences"][0]["conversation_id"], headers=bob[2]
        ).json()
        assert scheduled_result["turns"][0]["sources"]
        assert (
            client.get(base + "/schedules/" + scheduled["id"] + "/occurrences", headers=alice[2]).status_code
            == 404
        )
        assert len(received) == 6
