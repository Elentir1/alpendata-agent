"""Personal reviews authorize exactly one Graph request for an immutable version."""

import base64
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Event

import pytest
from requests import Timeout
from test_documents import example_pdf, start_document_turn
from test_microsoft_connections import connected_service as connected_service
from test_microsoft_connections import start
from test_sharepoint_documents import download_service as download_service
from test_sharepoint_documents import response

from alpendata_api.chat_worker import ChatWorker
from alpendata_api.microsoft_data import CALLBACK
from alpendata_api.models import Conversation


class EmailHTTP:
    def __init__(self):
        self.calls = []
        self.outcome = 202
        self.started = self.release = None

    def request(self, method, url, **kwargs):
        assert method == "POST" and url == "https://graph.microsoft.com/v1.0/me/sendMail"
        assert kwargs["allow_redirects"] is False and kwargs["timeout"] == 20
        assert self.trust_env is False
        self.calls.append(kwargs)
        if self.started:
            self.started.set()
            assert self.release.wait(15)
        if self.outcome == "timeout":
            raise Timeout("Synthetic response lost after dispatch")
        return response(self.outcome)


@pytest.fixture
def email_service(download_service):
    app, client, settings, provider, graph, org, alice, bob = download_service
    http = EmailHTTP()
    graph.session = http
    path = start_document_turn(download_service)
    worker = ChatWorker(settings, app.state.session_factory, runtime=object())
    job = worker.claim()
    artifact = worker.tool(
        job,
        [],
        {
            "kind": "document",
            "filename": "Séance.pdf",
            "content_base64": base64.b64encode(example_pdf()).decode(),
        },
    )["body"]
    payload = {
        "kind": "mail_draft",
        "to": ["client@example.com"],
        "subject": "Votre séance",
        "body": "Bonjour, voici votre support de séance.",
        "attachment_ids": [artifact["id"]],
    }
    result = worker.tool(job, [], payload)
    assert result["status"] == 200, result
    draft = result["body"]
    return download_service, http, path, worker, job, payload, draft


def permit_email(service):
    _, client, _, provider, _, org, alice, bob = service
    policy_path = f"/api/organizations/{org}/policy"
    policy = client.get(policy_path, headers=alice[2]).json()
    assert (
        client.put(
            policy_path,
            headers=alice[2],
            json={
                "version": policy["version"],
                "allowed_capabilities": list(dict.fromkeys([*policy["allowed_capabilities"], "mail_send"])),
            },
        ).status_code
        == 200
    )
    provider.http_client.scopes = {"openid", "profile", "offline_access", "Mail.Send"}
    flow = start(client, provider.http_client, org, bob, capabilities=("mail_send",))
    assert client.post(CALLBACK, data=flow, follow_redirects=False).status_code == 303


def test_email_review_is_personal_versioned_and_never_sent_by_the_model(email_service):
    service, http, conversation_path, worker, job, payload, draft = email_service
    app, client, _, provider, _, org, alice, bob = service
    base = f"/api/organizations/{org}"
    path = base + "/emails/" + draft["id"]
    assert not http.calls
    assert client.get(path, headers=alice[2]).status_code == 404
    assert (
        client.post(path + "/send", headers=alice[2], json={"version": 1, "confirmed": True}).status_code
        == 404
    )
    assert client.get(conversation_path, headers=bob[2]).json()["turns"][0]["emails"][0]["id"] == draft["id"]
    assert worker.tool(job, [], payload)["body"]["id"] == draft["id"]
    assert worker.tool(job, [], {**payload, "from": "colleague@example.com"})["status"] == 400
    assert worker.tool(job, [], {**payload, "to": ["A name without an email"]})["status"] == 400
    assert (
        worker.tool(job, [], {**payload, "attachment_ids": ["00000000-0000-0000-0000-000000000001"]})[
            "status"
        ]
        == 404
    )
    with app.state.session_factory.begin() as db:
        conversation = db.get(Conversation, conversation_path.rsplit("/", 1)[-1])
        conversation.tool_revision = 2
    assert worker.tool(job, [], payload)["status"] == 403
    with app.state.session_factory.begin() as db:
        db.get(Conversation, conversation_path.rsplit("/", 1)[-1]).tool_revision = 3
    assert (
        client.post(
            base + "/microsoft/connect", headers=bob[2], json={"capabilities": ["mail_send"]}
        ).status_code
        == 403
    )
    assert client.post(path + "/send", headers=bob[2], json={"version": 1}).status_code == 422
    assert (
        client.post(path + "/send", headers=bob[2], json={"version": 1, "confirmed": False}).status_code
        == 422
    )
    denied = client.post(path + "/send", headers=bob[2], json={"version": 1, "confirmed": True}).json()
    assert denied["attempts"][-1]["error_code"] == "company_policy_denied"
    assert not http.calls
    permit_email(service)
    edited_message = {
        **draft["message"],
        "to": ["reviewed@example.com"],
        "cc": ["copy@example.com"],
        "bcc": ["private@example.com"],
        "subject": "Séance validée",
    }
    edited = client.patch(path, headers=bob[2], json={"version": 1, "message": edited_message}).json()
    assert edited["version"] == 2
    assert (
        client.patch(path, headers=bob[2], json={"version": 1, "message": draft["message"]}).status_code
        == 409
    )
    assert worker.tool(job, [], payload)["body"]["message"] == edited_message
    result = client.post(path + "/send", headers=bob[2], json={"version": 2, "confirmed": True}).json()
    assert result["attempts"][-1]["status"] == "accepted" and not result["editable"]
    assert len(http.calls) == 1
    sent = http.calls[0]["json"]["message"]
    assert sent["subject"] == edited_message["subject"]
    assert sent["toRecipients"][0]["emailAddress"]["address"] == "reviewed@example.com"
    assert sent["bccRecipients"][0]["emailAddress"]["address"] == "private@example.com"
    assert base64.b64decode(sent["attachments"][0]["contentBytes"]) == example_pdf()
    assert "from" not in sent and "sender" not in sent
    assert http.calls[0]["headers"]["Authorization"] == "Bearer synthetic-access-" + bob[1]
    assert (
        client.post(path + "/send", headers=bob[2], json={"version": 2, "confirmed": True}).json() == result
    )
    assert (
        client.patch(path, headers=bob[2], json={"version": 2, "message": edited_message}).status_code == 409
    )
    assert len(http.calls) == 1


@pytest.mark.linux_only
def test_concurrent_send_and_lost_graph_response_never_dispatch_twice(email_service, request):
    if not request.config.getoption("--postgresql-bin"):
        pytest.skip("Requires real PostgreSQL row locks")
    service, http, _, _, _, _, draft = email_service
    _, client, _, _, _, org, _, bob = service
    permit_email(service)
    http.outcome = "timeout"
    http.started, http.release = Event(), Event()
    path = f"/api/organizations/{org}/emails/{draft['id']}"

    def send():
        return client.post(path + "/send", headers=bob[2], json={"version": 1, "confirmed": True})

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(send)
        assert http.started.wait(10)
        second = pool.submit(send)
        try:
            with pytest.raises(TimeoutError):
                second.result(timeout=2)
        finally:
            http.release.set()
        first_result, second_result = first.result(timeout=15), second.result(timeout=15)
    assert first_result.json()["attempts"][-1]["status"] == "unknown"
    assert second_result.status_code == 200
    assert client.get(path, headers=bob[2]).json()["attempts"][-1]["status"] == "unknown"
    assert send().status_code == 200
    assert len(http.calls) == 1
    assert (
        client.patch(path, headers=bob[2], json={"version": 1, "message": draft["message"]}).status_code
        == 409
    )
