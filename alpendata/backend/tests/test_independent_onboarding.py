import json
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest
from test_model_gateway import completion
from test_runtime import model_http

from alpendata_api.accounts import provision
from alpendata_api.auth import issue_session
from alpendata_api.chat_worker import ChatWorker
from alpendata_api.model_gateway import ModelGateway, ModelSettings
from alpendata_api.models import Conversation, RoutineSchedule, User, now
from alpendata_api.runtime import RuntimeSettings
from alpendata_api.schedule_worker import ScheduleWorker
from alpendata_api.settings import Settings

pytestmark = pytest.mark.linux_only


def test_independent_account_completes_proposals_trial_and_schedule_in_real_hermes(
    service_factory, database_url, request
):
    image = request.config.getoption("--runtime-image")
    if not image or not request.config.getoption("--postgresql-bin"):
        pytest.skip("Requires OCI image and PostgreSQL")
    proposals = [
        {
            "template": kind,
            "title": title,
            "benefit": "Prepare a coaching workshop",
            "focus": "New manager workshop",
        }
        for kind, title in (("work_process", "Workshop process"), ("work_checklist", "Workshop checklist"))
    ]

    def respond(body):
        names = {tool["function"]["name"] for tool in body.get("tools", [])}
        assert not {"alpendata_mail", "alpendata_calendar", "alpendata_files", "alpendata_send_email"} & names
        if "alpendata_propose_routines" in names and not any(
            message["role"] == "tool" for message in body["messages"]
        ):
            answer = completion(body, content=None)
            answer["choices"][0]["finish_reason"] = "tool_calls"
            answer["choices"][0]["message"]["tool_calls"] = [
                {
                    "id": uuid4().hex[:9],
                    "type": "function",
                    "function": {
                        "name": "alpendata_propose_routines",
                        "arguments": json.dumps({"proposals": proposals}),
                    },
                }
            ]
            return 200, answer, {}
        return (
            200,
            completion(
                body,
                content="Draft from your workshop brief: define objectives and prepare exercises. "
                "Review feedback. No external source consulted.",
            ),
            {},
        )

    with (
        tempfile.TemporaryDirectory(prefix="alpendata-independent-") as state,
        model_http(respond) as (transport, received, _),
    ):
        settings = Settings(
            database_url=database_url,
            model=ModelSettings("mistral", "mistral-small-latest", "synthetic"),
            runtime=RuntimeSettings(Path(state), image),
        )
        with service_factory(settings) as (app, client):
            with app.state.session_factory.begin() as db:
                _, token = provision(db, "coach@example.com", "Independent coach")
            origin = {"Origin": settings.public_origin}
            assert (
                client.post(
                    "/api/auth/password/activate",
                    headers=origin,
                    json={"token": token, "password": "A private coaching passphrase 42!"},
                ).status_code
                == 204
            )
            company = client.post(
                "/api/organizations", headers=origin, json={"name": "Independent coaching"}
            ).json()["id"]
            base = f"/api/organizations/{company}"
            assert (
                client.put(
                    base + "/onboarding",
                    headers=origin,
                    json={"language": "en", "role": "Coach", "needs": "Prepare workshops"},
                ).status_code
                == 200
            )
            planning = client.post(
                base + "/onboarding/proposals",
                headers=origin,
                json={
                    "request_id": str(uuid4()),
                    "language": "en",
                    "refinement": "Prepare a new manager workshop",
                },
            )
            assert planning.status_code == 202, planning.text
            worker = ChatWorker(
                settings, app.state.session_factory, gateway=ModelGateway(settings.model, session=transport)
            )
            assert worker.run_once()
            detail = client.get(base + "/chat/conversations/" + planning.json()["conversation"]["id"]).json()
            assert len(detail["proposals"]) == 2 and detail["turns"][0]["status"] == "completed"
            trial = client.post(
                base + "/routines/" + detail["proposals"][0]["id"] + "/trial",
                headers=origin,
                json={"request_id": str(uuid4())},
            )
            assert trial.status_code == 202, trial.text
            assert worker.run_once()
            trial = trial.json()
            detail = client.get(base + "/chat/conversations/" + trial["conversation_id"]).json()
            assert detail["trials"][0]["requires_sources"] is False and detail["turns"][0]["sources"] == []
            scheduled = client.post(
                base + "/schedules",
                headers=origin,
                json={
                    "request_id": str(uuid4()),
                    "reviewed_trial_id": trial["id"],
                    "reviewed": True,
                    "frequency": "daily",
                    "local_time": "09:00",
                    "timezone": "Europe/Zurich",
                },
            )
            assert scheduled.status_code == 201, scheduled.text
            with app.state.session_factory.begin() as db:
                db.get(RoutineSchedule, scheduled.json()["id"]).next_run_at = now() - 1
                assert db.get(Conversation, trial["conversation_id"]).capabilities == []
                other, _ = provision(db, "other@example.com", "Other", organization_id=company)
                other_auth = {
                    "Authorization": "Bearer " + issue_session(db, db.get(User, other.user_id), 3600)
                }
            assert (
                client.get(
                    base + "/chat/conversations/" + trial["conversation_id"], headers=other_auth
                ).status_code
                == 404
            )
            assert ScheduleWorker(settings, app.state.session_factory).tick() == 1
            assert worker.run_once()
            runs = client.get(base + "/schedules/" + scheduled.json()["id"] + "/occurrences").json()
            assert runs["occurrences"][0]["status"] == "completed", runs
            assert received
