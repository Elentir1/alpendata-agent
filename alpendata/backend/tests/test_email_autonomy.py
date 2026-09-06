"""Explicit personal and company authority is checked again for every send."""

from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Event
from uuid import uuid4

import pytest
from test_email_reviews import email_service as email_service
from test_email_reviews import permit_email
from test_microsoft_connections import connected_service as connected_service
from test_sharepoint_documents import download_service as download_service

from alpendata_api.chat_worker import ChatWorker
from alpendata_api.connections import MicrosoftReader
from alpendata_api.models import Conversation


def enable_autonomy(service):
    _, client, _, _, _, org, alice, bob = service
    permit_email(service)
    base = f"/api/organizations/{org}"
    policy = client.get(base + "/policy", headers=alice[2]).json()
    result = client.put(
        base + "/policy",
        headers=alice[2],
        json={
            "version": policy["version"],
            "allowed_capabilities": list(dict.fromkeys([*policy["allowed_capabilities"], "mail_autonomous"])),
        },
    )
    assert result.status_code == 200, result.text
    personal = client.get(base + "/action-policy", headers=bob[2]).json()
    result = client.put(
        base + "/action-policy",
        headers=bob[2],
        json={
            "version": personal["version"],
            "email_mode": "automatic",
            "acknowledged": True,
        },
    )
    assert result.status_code == 200 and result.json()["automatic_available"], result.text
    return result.json()


def queue_email(service):
    _, client, _, _, _, org, _, bob = service
    base = f"/api/organizations/{org}"
    assert (
        client.put(
            base + "/onboarding",
            headers=bob[2],
            json={"language": "en", "role": "Coach", "needs": "Client follow-up"},
        ).status_code
        == 200
    )
    conversation = client.post(base + "/chat/conversations", headers=bob[2], json={"language": "en"}).json()
    path = base + "/chat/conversations/" + conversation["id"]
    assert (
        client.post(
            path + "/turns",
            headers=bob[2],
            json={
                "request_id": str(uuid4()),
                "message": "Send client@example.com an email titled Session confirming our coaching session.",
            },
        ).status_code
        == 202
    )
    return path


def automatic_job(email_service):
    service, http, _, old_worker, old_job, _, _ = email_service
    app, _, settings, provider, graph, _, _, _ = service
    old_worker.finish(old_job, result={"response": "Draft ready"})
    enable_autonomy(service)
    path = queue_email(service)
    worker = ChatWorker(
        settings,
        app.state.session_factory,
        runtime=object(),
        microsoft=MicrosoftReader(settings, app.state.session_factory, provider, graph),
    )
    job = worker.claim()
    payload = {
        "kind": "mail_draft",
        "to": ["client@example.com"],
        "subject": "Session",
        "body": "Our session is confirmed.",
    }
    draft = worker.tool(job, [], payload)["body"]
    return service, http, worker, job, path, draft, payload


def test_autonomy_is_opted_in_personally_frozen_in_conversations_and_revocable(email_service):
    service, http, old_path, old_worker, old_job, _, old_draft = email_service
    app, client, _, _, _, org, alice, bob = service
    base = f"/api/organizations/{org}"
    initial = client.get(base + "/action-policy", headers=bob[2]).json()
    assert initial["email_mode"] == "confirm" and not initial["automatic_allowed"]
    assert (
        client.put(
            base + "/action-policy",
            headers=bob[2],
            json={"version": 0, "email_mode": "automatic", "acknowledged": True},
        ).status_code
        == 403
    )
    policy = enable_autonomy(service)
    assert client.get(base + "/action-policy", headers=alice[2]).json()["email_mode"] == "confirm"
    assert (
        client.put(
            base + "/action-policy", headers=bob[2], json={"version": 0, "email_mode": "confirm"}
        ).status_code
        == 409
    )
    assert (
        old_worker.tool(old_job, [], {"kind": "mail_send", "draft_id": old_draft["id"], "version": 1})[
            "status"
        ]
        == 403
    )
    with app.state.session_factory.begin() as db:
        old = db.get(Conversation, old_path.rsplit("/", 1)[-1])
        assert not old.email_send_enabled
        old_prompt = old.system_prompt
    # Returning to confirmation requires no broad-action acknowledgement.
    off = client.put(
        base + "/action-policy", headers=bob[2], json={"version": policy["version"], "email_mode": "confirm"}
    ).json()
    assert (
        client.put(
            base + "/action-policy",
            headers=bob[2],
            json={"version": off["version"], "email_mode": "automatic"},
        ).status_code
        == 409
    )
    service, http, worker, job, path, draft, payload = automatic_job(email_service)
    call = {"kind": "mail_send", "draft_id": draft["id"], "version": draft["version"]}
    assert worker.tool(job, [], {**call, "draft_id": old_draft["id"]})["status"] == 403
    result = worker.tool(job, [], call)
    assert result["status"] == 200, result
    assert result["body"]["attempts"][-1]["initiator"] == "agent"
    assert result["body"]["attempts"][-1]["autonomy_version"] > 0
    assert worker.tool(job, [], call)["body"] == result["body"]
    assert len(http.calls) == 1
    policy = client.get(base + "/action-policy", headers=bob[2]).json()
    assert (
        client.put(
            base + "/action-policy",
            headers=bob[2],
            json={"version": policy["version"], "email_mode": "confirm"},
        ).status_code
        == 200
    )
    assert worker.tool(job, [], call)["body"]["error"] == "email_confirmation_required"
    with app.state.session_factory.begin() as db:
        assert db.get(Conversation, old_path.rsplit("/", 1)[-1]).system_prompt == old_prompt
        assert db.get(Conversation, path.rsplit("/", 1)[-1]).email_send_enabled
    assert len(http.calls) == 1
    enable_autonomy(service)
    http.outcome = "timeout"
    uncertain = worker.tool(job, [], {**payload, "subject": "Next session"})["body"]
    result = worker.tool(job, [], {"kind": "mail_send", "draft_id": uncertain["id"], "version": 1})
    assert result["body"]["attempts"][-1]["status"] == "unknown"
    replacement = worker.tool(job, [], {**payload, "subject": "Next session again"})["body"]
    result = worker.tool(job, [], {"kind": "mail_send", "draft_id": replacement["id"], "version": 1})
    assert result["body"]["error"] == "email_send_unresolved"
    company = client.get(base + "/policy", headers=alice[2]).json()
    assert (
        client.put(
            base + "/policy",
            headers=alice[2],
            json={
                "version": company["version"],
                "allowed_capabilities": [
                    value for value in company["allowed_capabilities"] if value != "mail_autonomous"
                ],
            },
        ).status_code
        == 200
    )
    assert worker.tool(job, [], call)["body"]["error"] == "company_policy_denied"
    assert len(http.calls) == 2


@pytest.mark.linux_only
def test_disabling_autonomy_waits_for_inflight_send_and_blocks_subsequent_calls(email_service, request):
    if not request.config.getoption("--postgresql-bin"):
        pytest.skip("Requires PostgreSQL row locks")
    service, http, worker, job, _, draft, payload = automatic_job(email_service)
    _, client, _, _, _, org, _, bob = service
    path = f"/api/organizations/{org}/action-policy"
    policy = client.get(path, headers=bob[2]).json()
    http.started, http.release = Event(), Event()
    with ThreadPoolExecutor(max_workers=2) as pool:
        send = pool.submit(worker.tool, job, [], {"kind": "mail_send", "draft_id": draft["id"], "version": 1})
        assert http.started.wait(10)
        revoke = pool.submit(
            client.put, path, headers=bob[2], json={"version": policy["version"], "email_mode": "confirm"}
        )
        try:
            with pytest.raises(TimeoutError):
                revoke.result(timeout=2)
        finally:
            http.release.set()
        assert revoke.result(timeout=15).status_code == 200
        assert send.result(timeout=15)["status"] in (200, 403, 409)
    receipt = client.get(f"/api/organizations/{org}/emails/{draft['id']}", headers=bob[2]).json()
    assert receipt["attempts"][-1]["status"] == "accepted"
    other = worker.tool(job, [], {**payload, "subject": "Another session"})["body"]
    assert worker.tool(job, [], {"kind": "mail_send", "draft_id": other["id"], "version": 1})["status"] == 403
    assert len(http.calls) == 1
