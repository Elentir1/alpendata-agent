"""Sending routines require an explicit envelope, observed reads and a real dispatch receipt."""

import json
import tempfile
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from model_http import completion, model_http
from test_email_autonomy import enable_autonomy
from test_email_reviews import EmailHTTP
from test_email_verification import read_consent
from test_microsoft_connections import connected_service as connected_service
from test_routines import PROPOSALS
from test_routines import routine_service as routine_service
from test_schedules import activation, make_due

from alpendata_api.chat_worker import ChatWorker
from alpendata_api.connections import MicrosoftReader
from alpendata_api.model_gateway import ModelGateway
from alpendata_api.models import ChatTurn, Conversation, RoutineSchedule, now
from alpendata_api.runtime import RuntimeSettings
from alpendata_api.schedule_worker import ScheduleWorker

DELIVERY = {"to": ["coach@example.com"], "subject": "Client briefing"}


class DeliveryHTTP:
    def __init__(self, reading):
        self.reading, self.sending = reading, EmailHTTP()

    def request(self, method, url, **kwargs):
        target = self.sending if method == "POST" else self.reading
        target.trust_env = self.trust_env
        response = target.request(method, url, **kwargs)
        if method == "GET":
            content = response.json()
            content["value"][0].update(
                subject="Client coaching request",
                bodyPreview="Can we plan a session?",
                webLink="https://outlook.office.com/mail/example",
            )
            response._content = json.dumps(content).encode()
        return response


def prepare_delivery(service):
    app, client, settings, provider, graph, org, _, bob = service
    enable_autonomy(service)
    read_consent(service)
    base = f"/api/organizations/{org}"
    client.put(
        base + "/onboarding", headers=bob[2], json={"language": "en", "role": "Coach", "needs": "Briefing"}
    )
    planning = client.post(
        base + "/onboarding/proposals",
        headers=bob[2],
        json={
            "request_id": str(uuid4()),
            "language": "en",
            "refinement": "Email a briefing to my team",
        },
    )
    assert planning.status_code == 202, planning.text
    http = DeliveryHTTP(graph.session)
    graph.session = http
    worker = ChatWorker(
        settings,
        app.state.session_factory,
        runtime=object(),
        microsoft=MicrosoftReader(settings, app.state.session_factory, provider, graph),
    )
    job = worker.claim()
    proposals = [{**PROPOSALS[0], "template": "mail_briefing_delivery"}, PROPOSALS[1]]
    result = worker.tool(job, ["mail"], {"kind": "routine_proposals", "proposals": proposals})
    assert result["status"] == 200, result
    assert result["body"]["proposals"][0]["sends_email"]
    worker.finish(job, result={"response": "Choose and confirm your sending trial."})
    return worker, http, base, result["body"]["proposals"][0]


def start_trial(client, path, headers):
    body = {"request_id": str(uuid4()), "email_delivery": DELIVERY, "email_send_confirmed": True}
    response = client.post(path, headers=headers, json=body)
    assert response.status_code == 202, response.text
    return body, response.json()


def test_trial_envelope_receipts_idempotency_and_revocation(routine_service):
    app, client, settings, _, _, _, alice, bob = routine_service
    worker, http, base, proposal = prepare_delivery(routine_service)
    path = base + f"/routines/{proposal['id']}/trial"
    assert client.post(path, headers=bob[2], json={"request_id": str(uuid4())}).status_code == 409
    body, trial = start_trial(client, path, bob[2])
    assert client.post(path, headers=alice[2], json=body).status_code == 404
    assert client.post(path, headers=bob[2], json=body).json() == trial
    assert (
        client.post(
            path, headers=bob[2], json={**body, "email_delivery": {**DELIVERY, "to": ["other@example.com"]}}
        ).status_code
        == 409
    )
    job = worker.claim()

    def draft(**changes):
        result = worker.tool(job, ["mail"], {"kind": "mail_draft", **DELIVERY, "body": "Briefing", **changes})
        assert result["status"] == 200, result
        return result["body"]

    def send(item):
        return worker.tool(
            job, ["mail"], {"kind": "mail_send", "draft_id": item["id"], "version": item["version"]}
        )

    original = draft()
    assert send(original)["body"]["error"] == "routine_sources_missing"
    assert worker.tool(job, ["mail"], {"capability": "mail", "arguments": {}})["status"] == 200
    for changes in ({"to": ["other@example.com"]}, {"cc": ["other@example.com"]}, {"subject": "Changed"}):
        assert send(draft(**changes))["body"]["error"] == "routine_email_envelope_changed"
    assert not http.sending.calls
    sent = send(original)
    assert sent["body"]["attempts"][0]["status"] == "accepted"
    assert send(original)["status"] == 200 and len(http.sending.calls) == 1
    assert send(draft(body="Another briefing"))["body"]["error"] == "routine_email_already_attempted"
    worker.finish(job, result={"response": "Accepted"})
    result = client.post(base + "/schedules", headers=bob[2], json=activation(trial))
    assert result.json()["detail"] == "routine_email_confirmation_required"
    intent = {**activation(trial), "email_delivery_confirmed": True}
    result = client.post(base + "/schedules", headers=bob[2], json=intent)
    assert result.status_code == 201, result.text
    schedule = result.json()
    assert schedule["email_delivery"] == DELIVERY
    assert client.post(base + "/schedules", headers=bob[2], json=intent).json() == schedule
    first_due = now() - 120
    make_due(app, schedule["id"], first_due)
    assert ScheduleWorker(settings, app.state.session_factory).tick() == 1
    with app.state.session_factory() as db:
        queued = db.query(ChatTurn).filter_by(owner_id=bob[0], status="queued").one()
        queued_id = queued.id
        assert db.get(Conversation, queued.conversation_id).email_delivery == DELIVERY
    personal = client.get(base + "/action-policy", headers=bob[2]).json()
    assert (
        client.put(
            base + "/action-policy",
            headers=bob[2],
            json={"version": personal["version"], "email_mode": "confirm"},
        ).status_code
        == 200
    )
    with app.state.session_factory() as db:
        assert db.get(RoutineSchedule, schedule["id"]).status == "blocked"
        assert db.get(ChatTurn, queued_id).status == "cancelled"
    current = client.get(base + "/action-policy", headers=bob[2]).json()
    assert (
        client.put(
            base + "/action-policy",
            headers=bob[2],
            json={
                "version": current["version"],
                "email_mode": "automatic",
                "acknowledged": True,
            },
        ).status_code
        == 200
    )
    with app.state.session_factory() as db:
        assert db.get(RoutineSchedule, schedule["id"]).status == "blocked"
    # A successful read and an unsupported model claim cannot qualify a sending trial.
    _, missing = start_trial(client, path, bob[2])
    job = worker.claim()
    worker.tool(job, ["mail"], {"capability": "mail", "arguments": {}})
    worker.finish(job, result={"response": "Sent (unsupported claim)"})
    detail = client.get(base + "/chat/conversations/" + missing["conversation_id"], headers=bob[2]).json()
    assert detail["turns"][0]["error_code"] == "routine_email_not_accepted"
    assert not detail["trials"][0]["delivery_accepted"]

    # A reviewed replacement can change the envelope, but cannot overwrite a newer schedule.
    changed_delivery = {"to": ["team@example.com"], "subject": "Team briefing"}
    changed = client.post(
        path,
        headers=bob[2],
        json={
            "request_id": str(uuid4()),
            "email_delivery": changed_delivery,
            "email_send_confirmed": True,
        },
    ).json()
    job = worker.claim()
    worker.tool(job, ["mail"], {"capability": "mail", "arguments": {}})
    assert send(draft(**changed_delivery))["body"]["attempts"][0]["status"] == "accepted"
    worker.finish(job, result={"response": "Replacement briefing accepted"})
    current = client.get(base + "/schedules", headers=bob[2]).json()["schedules"][0]
    resumed = client.post(
        base + f"/schedules/{schedule['id']}/resume", headers=bob[2], json={"version": current["version"]}
    ).json()
    make_due(app, schedule["id"], first_due + 60)
    assert ScheduleWorker(settings, app.state.session_factory).tick() == 1
    with app.state.session_factory() as db:
        old_occurrence = db.query(ChatTurn).filter_by(owner_id=bob[0], status="queued").one().id
    intent = {**activation(changed), "email_delivery_confirmed": True}
    assert (
        client.post(base + "/schedules", headers=bob[2], json=intent).json()["detail"]
        == "routine_version_changed"
    )
    intent["replaces_schedule_version"] = resumed["version"]
    replacement = client.post(base + "/schedules", headers=bob[2], json=intent)
    assert replacement.status_code == 201, replacement.text
    assert replacement.json()["email_delivery"] == changed_delivery
    with app.state.session_factory() as db:
        assert db.get(ChatTurn, old_occurrence).status == "cancelled"

    # Uncertain sending is not a reviewed success and cannot be bypassed with another message.
    _, uncertain = start_trial(client, path, bob[2])
    job = worker.claim()
    worker.tool(job, ["mail"], {"capability": "mail", "arguments": {}})
    http.sending.outcome = "timeout"
    assert send(draft())["body"]["attempts"][0]["status"] == "unknown"
    assert send(draft(body="Replacement after uncertainty"))["status"] == 409
    worker.finish(job, result={"response": "Outcome uncertain"})
    invalid_activation = {**activation(uncertain), "email_delivery_confirmed": True}
    assert (
        client.post(base + "/schedules", headers=bob[2], json=invalid_activation).json()["detail"]
        == "routine_trial_required"
    )


@pytest.mark.linux_only
def test_real_hermes_sends_trial_and_scheduled_occurrence_with_reviewed_envelope(routine_service, request):
    image = request.config.getoption("--runtime-image")
    if not image or not request.config.getoption("--postgresql-bin"):
        pytest.skip("Requires real OCI image and PostgreSQL")
    app, client, settings, provider, graph, _, alice, bob = routine_service
    _, http, base, proposal = prepare_delivery(routine_service)
    _, trial = start_trial(client, base + f"/routines/{proposal['id']}/trial", bob[2])

    def respond(body):
        names = {tool["function"]["name"] for tool in body.get("tools", [])}
        assert "alpendata_send_email" in names
        assert "synthetic-access-" not in json.dumps(body)
        answers = [json.loads(item["content"]) for item in body["messages"] if item["role"] == "tool"]
        if len(answers) == 3:
            assert answers[-1]["result"]["attempts"][0]["status"] == "accepted", answers
            return 200, completion(body, content="Microsoft accepted this briefing."), {}
        actions = [
            ("alpendata_mail", {}),
            (
                "alpendata_prepare_email",
                {
                    **DELIVERY,
                    "body": "A client asked about coaching. Source: https://outlook.office.com/mail/example",
                },
            ),
        ]
        name, arguments = (
            actions[len(answers)]
            if len(answers) < 2
            else (
                "alpendata_send_email",
                {"draft_id": answers[1]["result"]["id"], "version": answers[1]["result"]["version"]},
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
        tempfile.TemporaryDirectory(prefix="alpendata-delivery-") as state,
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
        detail = client.get(base + "/chat/conversations/" + trial["conversation_id"], headers=bob[2]).json()
        assert detail["trials"][0]["delivery_accepted"], detail
        result = client.post(
            base + "/schedules", headers=bob[2], json={**activation(trial), "email_delivery_confirmed": True}
        )
        assert result.status_code == 201, result.text
        make_due(app, result.json()["id"], now())
        assert ScheduleWorker(settings, app.state.session_factory).tick() == 1
        assert worker.run_once()
        runs = client.get(base + f"/schedules/{result.json()['id']}/occurrences", headers=bob[2]).json()[
            "occurrences"
        ]
        assert runs[0]["status"] == "completed", runs
        assert (
            client.get(
                base + "/chat/conversations/" + runs[0]["conversation_id"], headers=alice[2]
            ).status_code
            == 404
        )
        assert len(http.sending.calls) == 2
        for call in http.sending.calls:
            assert call["headers"]["Authorization"] == "Bearer synthetic-access-" + bob[1]
            assert call["json"]["message"]["subject"] == DELIVERY["subject"]
            assert call["json"]["message"]["toRecipients"] == [
                {"emailAddress": {"address": DELIVERY["to"][0]}}
            ]
