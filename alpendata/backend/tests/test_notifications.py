"""Personal inbox derives from real scheduler/worker transactions, never model claims."""

from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select
from test_routines import connected_service as connected_service
from test_routines import routine_service as routine_service
from test_schedules import activation, make_due
from test_schedules import approved_trial as approved_trial

from alpendata_api.models import ChatTurn, PersonalNotification, now
from alpendata_api.schedule_worker import ScheduleWorker


def test_finished_results_are_private_and_read_state_survives_retries_and_license_removal(
    routine_service, approved_trial
):
    app, client, settings, _, _, org, admin, owner = routine_service
    trial, worker = approved_trial
    base = f"/api/organizations/{org}"
    path = base + "/notifications"
    schedule = client.post(base + "/schedules", headers=owner[2], json=activation(trial)).json()
    assert client.get(path).status_code == 401
    assert client.get(path, headers=owner[2]).json()["notifications"] == []
    make_due(app, schedule["id"], now() - 1)
    assert ScheduleWorker(settings, app.state.session_factory).tick() == 1
    assert client.get(path, headers=owner[2]).json()["unread"] == 0
    job = worker.claim()
    assert worker.tool(job, ["mail"], {"capability": "mail", "arguments": {}})["status"] == 200
    worker.finish(job, result={"response": "Private client briefing"})
    worker.finish(job, result={"response": "Must not emit twice"})
    result = client.get(path, headers=owner[2])
    assert result.headers["Cache-Control"] == "no-store"
    assert result.json()["unread"] == len(result.json()["notifications"]) == 1
    item = result.json()["notifications"][0]
    assert item["status"] == "completed" and item["conversation_id"]
    assert "Private client briefing" not in result.text
    assert client.get(path, headers=admin[2]).json()["notifications"] == []
    read_path = path + "/" + item["id"] + "/read"
    assert client.put(read_path, headers=admin[2], json={}).status_code == 404
    assert client.put(read_path, headers=owner[2], json={"owner_id": admin[0]}).status_code == 422
    other_org = client.post("/api/organizations", headers=admin[2], json={"name": "Other"}).json()["id"]
    assert (
        client.put(
            f"/api/organizations/{other_org}/notifications/{item['id']}/read", headers=admin[2], json={}
        ).status_code
        == 404
    )
    assert client.get(path + "?before=1", headers=owner[2]).status_code == 422
    failure_at = now() - 60
    ticker = ScheduleWorker(settings, app.state.session_factory)
    make_due(app, schedule["id"], failure_at)
    assert ticker.tick() == 1
    failed_job = worker.claim()
    worker.finish(failed_job, error="agent_execution_failed")
    worker.finish(failed_job, error="agent_execution_failed")
    make_due(app, schedule["id"], failure_at + 1)
    assert ticker.tick() == 1
    interrupted_job = worker.claim()
    with app.state.session_factory.begin() as db:
        db.get(ChatTurn, interrupted_job.id).lease_expires_at = now() - 1
    worker.recover_expired()
    worker.recover_expired()
    updates = client.get(path, headers=owner[2]).json()["notifications"]
    assert sorted(n["status"] for n in updates) == ["completed", "failed", "interrupted"]
    assert all(n["conversation_id"] for n in updates)
    changes = {"version": 1, "role": "member", "active": True, "licensed": False}
    assert client.patch(base + "/members/" + owner[0], headers=admin[2], json=changes).status_code == 200
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(client.put, read_path, headers=owner[2], json={}) for _ in range(2)]
        read = [f.result(timeout=15) for f in futures]
    assert all(r.status_code == 200 for r in read)
    assert read[0].json()["read_at"] == read[1].json()["read_at"]
    assert client.put(read_path, headers=owner[2], json={}).json() == read[0].json()
    # Revoking a seat can additionally block the schedule, but cannot resurrect the read result.
    listing = client.get(path, headers=owner[2]).json()
    assert next(n for n in listing["notifications"] if n["id"] == item["id"])["read_at"]
    assert client.get(path + "?count_only=true", headers=owner[2]).json()["unread"] == sum(
        n["read_at"] is None for n in listing["notifications"]
    )
    assert (
        client.patch(
            base + "/members/" + owner[0], headers=admin[2], json={**changes, "version": 2, "active": False}
        ).status_code
        == 200
    )
    assert client.get(path, headers=owner[2]).status_code == 404


def test_missed_and_blocked_tasks_notify_once_and_cursor_handles_equal_timestamps(
    routine_service, approved_trial
):
    app, client, settings, _, _, org, _, owner = routine_service
    trial, _ = approved_trial
    base = f"/api/organizations/{org}"
    path = base + "/notifications"
    schedule = client.post(base + "/schedules", headers=owner[2], json=activation(trial)).json()
    ticker = ScheduleWorker(settings, app.state.session_factory)
    stamp = now()
    for index in range(27):
        make_due(app, schedule["id"], stamp - 8000 - index)
        assert ticker.tick() == 1
        assert ticker.tick() == 0
    # Equal timestamps are ordinary during a batch; force them independently of wall-clock speed.
    with app.state.session_factory.begin() as db:
        rows = db.scalars(select(PersonalNotification)).all()
        assert len(rows) == 27
        for row in rows:
            row.created_at = stamp
    first = client.get(path, headers=owner[2]).json()
    assert first["unread"] == 27 and len(first["notifications"]) == 25
    assert all(row["status"] == "missed" and row["conversation_id"] is None for row in first["notifications"])
    assert client.delete(base + "/microsoft", headers=owner[2]).status_code == 204
    assert client.delete(base + "/microsoft", headers=owner[2]).status_code == 204
    latest = client.get(path, headers=owner[2]).json()
    assert latest["unread"] == 28
    cursor = first["next_before"]
    rest = client.get(path + f"?before={cursor['at']}&before_id={cursor['id']}", headers=owner[2]).json()
    # A concurrent new notification may fall on either side of the old cursor.
    missed = [row for row in first["notifications"] + rest["notifications"] if row["status"] == "missed"]
    assert len({row["id"] for row in missed}) == 27 and len(missed) == 27
    with app.state.session_factory() as db:
        blocked = db.scalars(
            select(PersonalNotification).where(PersonalNotification.status == "blocked")
        ).all()
        assert len(blocked) == 1 and blocked[0].turn_id is None
