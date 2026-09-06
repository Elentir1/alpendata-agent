"""Reviewed schedules retain their tool authority and stop when it is withdrawn."""

from uuid import uuid4

from test_email_autonomy import enable_autonomy
from test_email_verification import read_consent
from test_microsoft_connections import connected_service as connected_service
from test_routines import PROPOSALS
from test_routines import routine_service as routine_service
from test_schedules import activation, make_due

from alpendata_api.chat_worker import ChatWorker
from alpendata_api.connections import MicrosoftReader
from alpendata_api.models import ChatTurn, Conversation, RoutineSchedule, now
from alpendata_api.schedule_worker import ScheduleWorker


def test_personal_revocation_blocks_the_reviewed_schedule_and_its_queued_occurrence(routine_service):
    app, client, settings, provider, graph, org, _, bob = routine_service
    policy = enable_autonomy(routine_service)
    read_consent(routine_service)
    base = f"/api/organizations/{org}"
    assert (
        client.put(
            base + "/onboarding",
            headers=bob[2],
            json={"language": "en", "role": "Coach", "needs": "Client updates"},
        ).status_code
        == 200
    )
    planning = client.post(
        base + "/onboarding/proposals",
        headers=bob[2],
        json={"request_id": str(uuid4()), "language": "en", "refinement": "Prepare my daily briefing"},
    ).json()
    worker = ChatWorker(
        settings,
        app.state.session_factory,
        runtime=object(),
        microsoft=MicrosoftReader(settings, app.state.session_factory, provider, graph),
    )
    job = worker.claim()
    with app.state.session_factory.begin() as db:
        assert not db.get(Conversation, planning["conversation"]["id"]).email_send_enabled
    proposal = worker.tool(job, ["mail"], {"kind": "routine_proposals", "proposals": PROPOSALS})["body"][
        "proposals"
    ][0]
    worker.finish(job, result={"response": "Choose a task"})
    trial = client.post(
        base + "/routines/" + proposal["id"] + "/trial", headers=bob[2], json={"request_id": str(uuid4())}
    ).json()
    job = worker.claim()
    assert worker.tool(job, ["mail"], {"capability": "mail", "arguments": {}})["status"] == 200
    worker.finish(job, result={"response": "Reviewed briefing"})
    result = client.post(base + "/schedules", headers=bob[2], json=activation(trial))
    assert result.status_code == 201, result.text
    schedule = result.json()
    make_due(app, schedule["id"], now())
    assert ScheduleWorker(settings, app.state.session_factory).tick() == 1
    with app.state.session_factory.begin() as db:
        queued = db.query(ChatTurn).filter_by(owner_id=bob[0], status="queued").one()
        queued_id = queued.id
        assert db.get(Conversation, queued.conversation_id).email_send_enabled
    result = client.put(
        base + "/action-policy", headers=bob[2], json={"version": policy["version"], "email_mode": "confirm"}
    )
    assert result.status_code == 200
    with app.state.session_factory.begin() as db:
        assert db.get(RoutineSchedule, schedule["id"]).status == "blocked"
        assert db.get(ChatTurn, queued_id).status == "cancelled"
    assert worker.claim() is None
    enable_autonomy(routine_service)
    with app.state.session_factory.begin() as db:
        assert db.get(RoutineSchedule, schedule["id"]).status == "blocked"
