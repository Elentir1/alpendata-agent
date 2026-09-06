from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import select
from test_routines import PROPOSALS
from test_routines import connected_service as connected_service
from test_routines import routine_service as routine_service

from alpendata_api.chat_worker import ChatWorker
from alpendata_api.connections import MicrosoftReader
from alpendata_api.models import ChatTurn, RoutineOccurrence, RoutineSchedule, now
from alpendata_api.runtime import RuntimeFailure
from alpendata_api.schedule_time import Cadence, next_occurrence
from alpendata_api.schedule_worker import ScheduleWorker


def test_civil_schedule_skips_gaps_repeated_hours_and_weekends():
    def stamp(value):
        return int(datetime.fromisoformat(value).timestamp())

    daily = Cadence(frequency="daily", local_time="02:30", timezone="Europe/Zurich")
    assert next_occurrence(daily, stamp("2026-03-28T02:30:00+01:00")) == stamp("2026-03-30T02:30:00+02:00")
    first_fold = next_occurrence(daily, stamp("2026-10-24T02:30:00+02:00"))
    assert first_fold == stamp("2026-10-25T02:30:00+02:00")
    assert next_occurrence(daily, first_fold) == stamp("2026-10-26T02:30:00+01:00")
    weekdays = Cadence(frequency="weekdays", local_time="09:00", timezone="Europe/Zurich")
    assert next_occurrence(weekdays, stamp("2026-09-04T09:00:00+02:00")) == stamp("2026-09-07T09:00:00+02:00")
    weekly = Cadence(frequency="weekly", weekday=0, local_time="09:00", timezone="Europe/Zurich")
    assert next_occurrence(weekly, stamp("2026-09-07T09:00:00+02:00")) == stamp("2026-09-14T09:00:00+02:00")


@pytest.fixture
def approved_trial(routine_service):
    app, client, settings, provider, graph, org, _, bob = routine_service
    base = f"/api/organizations/{org}"
    client.put(
        base + "/onboarding",
        headers=bob[2],
        json={"language": "en", "role": "Coach", "needs": "Client follow-up"},
    )
    client.post(
        base + "/onboarding/proposals",
        headers=bob[2],
        json={"request_id": str(uuid4()), "language": "en", "refinement": "Help with client requests"},
    )
    worker = ChatWorker(
        settings,
        app.state.session_factory,
        runtime=object(),
        microsoft=MicrosoftReader(settings, app.state.session_factory, provider, graph),
    )
    job = worker.claim()
    proposal = worker.tool(job, ["mail"], {"kind": "routine_proposals", "proposals": PROPOSALS})["body"][
        "proposals"
    ][0]
    worker.finish(job, result={"response": "Choose a task"})
    trial = client.post(
        base + "/routines/" + proposal["id"] + "/trial", headers=bob[2], json={"request_id": str(uuid4())}
    ).json()
    job = worker.claim()
    assert worker.tool(job, ["mail"], {"capability": "mail", "arguments": {}})["status"] == 200
    worker.finish(job, result={"response": "Client briefing"})
    return trial, worker


def activation(trial):
    return {
        "request_id": str(uuid4()),
        "reviewed_trial_id": trial["id"],
        "replaces_schedule_version": trial.get("schedule_version"),
        "reviewed": True,
        "frequency": "weekdays",
        "local_time": "08:30",
        "timezone": "Europe/Zurich",
    }


def make_due(app, schedule_id, at):
    with app.state.session_factory.begin() as db:
        db.get(RoutineSchedule, schedule_id).next_run_at = at


def test_reviewed_schedule_is_private_idempotent_and_suspended_with_access(routine_service, approved_trial):
    app, client, settings, _, _, org, alice, bob = routine_service
    trial, worker = approved_trial
    base = f"/api/organizations/{org}"
    body = activation(trial)
    assert (
        client.post(base + "/schedules", headers=bob[2], json={**body, "reviewed": False}).status_code == 422
    )
    assert (
        client.post(
            base + "/schedules", headers=bob[2], json={**body, "timezone": "Nowhere/Invalid"}
        ).status_code
        == 422
    )
    assert client.post(base + "/schedules", headers=alice[2], json=body).status_code == 404
    response = client.post(base + "/schedules", headers=bob[2], json=body)
    assert response.status_code == 201, response.text
    schedule = response.json()
    assert client.post(base + "/schedules", headers=bob[2], json=body).json() == schedule
    assert client.get(base + "/schedules", headers=alice[2]).json()["schedules"] == []
    path = base + "/schedules/" + schedule["id"]
    assert client.get(path + "/occurrences", headers=alice[2]).status_code == 404
    at = now() - 1
    make_due(app, schedule["id"], at)
    ticker = ScheduleWorker(settings, app.state.session_factory)
    assert ticker.tick() == 1
    assert ScheduleWorker(settings, app.state.session_factory).tick() == 0
    job = worker.claim()
    paused = client.post(path + "/pause", headers=bob[2], json={"version": schedule["version"]}).json()
    assert paused["status"] == "paused" and paused["next_run_at"] is None
    with pytest.raises(RuntimeFailure, match="agent_cancelled"):
        worker.tool(job, ["mail"], {"capability": "mail", "arguments": {}})
    worker.finish(job, error="agent_cancelled")
    assert client.get(path + "/occurrences", headers=bob[2]).json()["occurrences"][0]["status"] == "cancelled"
    assert (
        client.post(path + "/resume", headers=bob[2], json={"version": schedule["version"]}).status_code
        == 409
    )
    resumed = client.post(path + "/resume", headers=bob[2], json={"version": paused["version"]}).json()
    assert resumed["status"] == "active" and resumed["next_run_at"] > now()
    edited = client.patch(
        path,
        headers=bob[2],
        json={
            "version": resumed["version"],
            "frequency": "weekly",
            "weekday": 2,
            "local_time": "10:15",
            "timezone": "Europe/Zurich",
        },
    ).json()
    assert edited["version"] > resumed["version"] and edited["weekday"] == 2
    assert edited["local_time"] == "10:15"
    make_due(app, schedule["id"], at - 1)
    assert ticker.tick() == 1
    client.delete(base + "/microsoft", headers=bob[2])
    blocked = client.get(base + "/schedules", headers=bob[2]).json()["schedules"][0]
    assert blocked["status"] == "blocked" and blocked["reason_code"] == "microsoft_reconnect_required"
    assert worker.claim() is None
    assert (
        client.post(path + "/resume", headers=bob[2], json={"version": blocked["version"]}).status_code == 409
    )
    assert (
        client.post(path + "/archive", headers=bob[2], json={"version": blocked["version"]}).json()["status"]
        == "archived"
    )
    assert client.get(base + "/schedules", headers=bob[2]).json()["schedules"] == []
    assert client.get(path + "/occurrences", headers=bob[2]).json()["occurrences"]


def test_missed_occurrences_are_not_replayed_and_repeated_failures_block(routine_service, approved_trial):
    app, client, settings, _, _, org, alice, bob = routine_service
    trial, worker = approved_trial
    path = f"/api/organizations/{org}/schedules"
    schedule = client.post(path, headers=bob[2], json=activation(trial)).json()
    ticker = ScheduleWorker(settings, app.state.session_factory)
    at = now()
    make_due(app, schedule["id"], at - 7201)
    assert ticker.tick(at) == 1 and worker.claim() is None
    assert (
        client.get(path + "/" + schedule["id"] + "/occurrences", headers=bob[2]).json()["occurrences"][0][
            "status"
        ]
        == "missed"
    )
    for offset in range(3):
        # One fixed clock gives each forced occurrence its own instant, regardless
        # of how many wall-clock seconds the preceding request consumed.
        make_due(app, schedule["id"], at - 20 + offset)
        assert ticker.tick(at) == 1
        job = worker.claim()
        # A model answer alone cannot turn an unperformed scheduled read into success.
        worker.finish(job, result={"response": "Unsupported claim of reading emails"})
        with app.state.session_factory() as db:
            assert db.get(ChatTurn, job.id).error_code == "routine_sources_missing"
    blocked = client.get(path, headers=bob[2]).json()["schedules"][0]
    assert blocked["status"] == "blocked" and blocked["reason_code"] == "routine_repeated_failures"
    assert ticker.tick(at) == 0
    repeat = client.post(
        f"/api/organizations/{org}/routines/" + blocked["proposal_id"] + "/trial",
        headers=bob[2],
        json={"request_id": str(uuid4())},
    ).json()
    job = worker.claim()
    worker.tool(job, ["mail"], {"capability": "mail", "arguments": {}})
    worker.finish(job, result={"response": "Reviewed new trial"})
    detail = client.get(
        f"/api/organizations/{org}/chat/conversations/" + repeat["conversation_id"], headers=bob[2]
    ).json()
    assert detail["trials"][0]["can_replace_schedule"] is True
    replacement = client.post(path, headers=bob[2], json=activation(repeat)).json()
    assert replacement["id"] == blocked["id"] and replacement["status"] == "active"
    assert replacement["version"] > blocked["version"]
    removed_license = client.patch(
        f"/api/organizations/{org}/members/" + bob[0],
        headers=alice[2],
        json={"version": 1, "role": "member", "active": True, "licensed": False},
    )
    assert removed_license.status_code == 200
    revoked = client.get(path, headers=bob[2]).json()["schedules"][0]
    assert revoked["status"] == "blocked" and revoked["reason_code"] == "agent_access_revoked"
    assert (
        client.post(
            path + "/" + revoked["id"] + "/resume", headers=bob[2], json={"version": revoked["version"]}
        ).status_code
        == 403
    )


@pytest.mark.linux_only
def test_concurrent_activation_and_ticks_create_one_occurrence(routine_service, approved_trial, request):
    if not request.config.getoption("--postgresql-bin"):
        pytest.skip("Requires PostgreSQL locks")
    app, client, settings, _, _, org, _, bob = routine_service
    trial, _ = approved_trial
    body = activation(trial)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = [
            pool.submit(client.post, f"/api/organizations/{org}/schedules", headers=bob[2], json=body)
            for _ in range(2)
        ]
        values = [response.result(timeout=20).json() for response in responses]
    assert values[0]["id"] == values[1]["id"]
    make_due(app, values[0]["id"], now() - 1)
    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = [pool.submit(ScheduleWorker(settings, app.state.session_factory).tick) for _ in range(2)]
        assert sum(reply.result(timeout=20) for reply in replies) == 1
    with app.state.session_factory() as db:
        rows = db.scalars(
            select(RoutineOccurrence).where(RoutineOccurrence.schedule_id == values[0]["id"])
        ).all()
        assert len(rows) == 1 and rows[0].turn_id
