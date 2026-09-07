import json
from uuid import uuid4

import pytest
from fastapi import HTTPException
from service_http import service_http
from test_microsoft_connections import connected_service as connected_service
from test_microsoft_connections import start
from test_routines import routine_service as routine_service

from alpendata_api.calendar_provider import dav_write
from alpendata_api.chat_worker import ChatWorker
from alpendata_api.connections import MicrosoftReader
from alpendata_api.infomaniak_dav import InfomaniakDav, opaque_path
from alpendata_api.microsoft_data import CALLBACK

EVENT = {
    "subject": "Client coaching",
    "start": "2026-10-05T10:00:00+02:00",
    "end": "2026-10-05T11:00:00+02:00",
    "attendees": ["client@example.com"],
}


def test_personal_calendar_review_never_replays_completed_or_unknown_writes(routine_service):
    app, client, settings, provider, graph, org, admin, owner = routine_service
    root = f"/api/organizations/{org}"
    policy = client.get(root + "/policy", headers=admin[2]).json()
    assert (
        client.put(
            root + "/policy",
            headers=admin[2],
            json={
                "version": policy["version"],
                "allowed_capabilities": [*policy["allowed_capabilities"], "calendar_write"],
            },
        ).status_code
        == 200
    )
    provider.http_client.scopes = {
        "openid",
        "profile",
        "offline_access",
        "Calendars.Read",
        "Calendars.ReadWrite",
    }
    flow = start(client, provider.http_client, org, owner, capabilities=("calendar", "calendar_write"))
    assert client.post(CALLBACK, data=flow, follow_redirects=False).status_code == 303
    client.put(
        root + "/onboarding", headers=owner[2], json={"language": "fr", "role": "Coach", "needs": "Meetings"}
    )
    conversation = client.post(root + "/chat/conversations", headers=owner[2], json={}).json()["id"]
    path = root + "/chat/conversations/" + conversation
    client.post(
        path + "/turns",
        headers=owner[2],
        json={"request_id": str(uuid4()), "message": "Prepare an appointment"},
    )
    worker = ChatWorker(
        settings,
        app.state.session_factory,
        runtime=object(),
        microsoft=MicrosoftReader(settings, app.state.session_factory, provider, graph),
    )
    job = worker.claim()
    outcome = [201]

    def respond(request):
        assert request["method"] == "POST" and request["path"] == "/v1.0/me/events"
        return outcome[0], {"Content-Type": "application/json"}, json.dumps({"id": "created-event"}).encode()

    with service_http(respond) as (transport, calls):
        graph.session = transport
        payload = {"kind": "calendar_action", "operation": "prepare", "event": EVENT}
        prepared = worker.tool(job, ["calendar"], payload)
        assert prepared["status"] == 200, prepared
        action = prepared["body"]
        assert not calls
        assert worker.tool(job, ["calendar"], payload)["body"]["id"] == action["id"]
        action_path = root + "/calendar-actions/" + action["id"]
        assert client.post(action_path + "/execute", headers=admin[2], json={"version": 1}).status_code == 404
        assert (
            worker.tool(
                job,
                ["calendar"],
                {"kind": "calendar_action", "operation": "execute", "action_id": action["id"], "version": 1},
            )["status"]
            == 403
        )
        result = client.post(action_path + "/execute", headers=owner[2], json={"version": 1})
        assert result.status_code == 200 and result.json()["status"] == "completed", result.text
        assert len(calls) == 1
        body = json.loads(calls[0]["body"])
        assert (
            body["transactionId"] and body["attendees"][0]["emailAddress"]["address"] == "client@example.com"
        )
        assert calls[0]["headers"]["Authorization"] == "Bearer synthetic-access-" + owner[1]
        assert (
            client.post(action_path + "/execute", headers=owner[2], json={"version": 1}).json()
            == result.json()
        )
        assert len(calls) == 1
        outcome[0] = 503
        unknown = worker.tool(
            job, ["calendar"], {**payload, "event": {**EVENT, "subject": "Another appointment"}}
        )["body"]
        unknown_path = root + "/calendar-actions/" + unknown["id"]
        assert (
            client.post(unknown_path + "/execute", headers=owner[2], json={"version": 1}).json()["status"]
            == "unknown"
        )
        assert (
            client.post(unknown_path + "/execute", headers=owner[2], json={"version": 1}).json()["status"]
            == "unknown"
        )
        assert len(calls) == 2
        assert (
            client.put(
                unknown_path, headers=owner[2], json={"version": 1, "message": unknown["message"]}
            ).status_code
            == 409
        )
        assert client.get(path, headers=owner[2]).json()["turns"][0]["calendar_actions"]


def test_dav_calendar_creation_uses_unique_uid_and_refuses_overwrite():
    credentials = {"calendar": {"username": "synthetic", "password": "synthetic"}}
    from alpendata_api.calendar_actions import EventInput

    data = EventInput.model_validate(EVENT).model_dump(mode="json")
    baseline = {"calendar_id": opaque_path("/calendars/personal/"), "organizer": "mailto:coach@example.com"}
    with service_http(
        lambda request: (201 if request["headers"].get("If-None-Match") == "*" else 412, {}, b"")
    ) as (transport, calls):
        result = dav_write(InfomaniakDav(transport), credentials, "one-request", data, baseline)
        assert result["event_id"] == opaque_path("/calendars/personal/one-request.ics")
        assert b"UID:one-request@agent.alpendata.ch" in calls[0]["body"]
        from icalendar import Calendar

        assert (
            str(Calendar.from_ical(calls[0]["body"]).walk("VEVENT")[0]["attendee"])
            == "mailto:client@example.com"
        )
    with service_http(lambda _: (412, {}, b"")) as (transport, calls):
        with pytest.raises(HTTPException):
            dav_write(InfomaniakDav(transport), credentials, "one-request", data, baseline)
        assert len(calls) == 1
