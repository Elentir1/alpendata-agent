"""Sent-copy evidence cannot grant delivery claims or authorize another send."""

import copy
import json
from datetime import datetime, timezone

from test_email_reviews import email_service as email_service
from test_email_reviews import permit_email
from test_microsoft_connections import connected_service as connected_service
from test_microsoft_connections import start
from test_sharepoint_documents import download_service as download_service
from test_sharepoint_documents import response

from alpendata_api.microsoft_data import CALLBACK
from alpendata_api.models import EmailAttempt


class SentHTTP:
    def __init__(self, original, sent):
        self.original, self.sent = original, sent
        self.reads = []
        self.next_link = None
        self.status = 200

    def request(self, method, url, **kwargs):
        if method == "POST":
            self.original.trust_env = self.trust_env
            return self.original.request(method, url, **kwargs)
        assert method == "GET" and url == "https://graph.microsoft.com/v1.0/me/mailFolders/sentitems/messages"
        assert kwargs["allow_redirects"] is False
        assert self.trust_env is False
        assert kwargs["params"]["$top"] == 100
        assert kwargs["params"]["$filter"].startswith("sentDateTime ge ")
        assert "internetMessageHeaders" in kwargs["params"]["$select"]
        self.reads.append(kwargs)
        return response(
            self.status, json.dumps({"value": self.sent, "@odata.nextLink": self.next_link}).encode()
        )


def read_consent(service):
    _, client, _, provider, _, org, _, bob = service
    provider.http_client.scopes = {"openid", "profile", "offline_access", "Mail.Send", "Mail.Read"}
    flow = start(client, provider.http_client, org, bob, capabilities=("mail", "mail_send"))
    assert client.post(CALLBACK, data=flow, follow_redirects=False).status_code == 303


def uncertain_message(email_service):
    service, http, _, _, _, _, draft = email_service
    app, client, _, _, graph, org, alice, bob = service
    permit_email(service)
    http.outcome = "timeout"
    path = f"/api/organizations/{org}/emails/{draft['id']}"
    result = client.post(path + "/send", headers=bob[2], json={"version": 1, "confirmed": True}).json()
    attempt = result["attempts"][-1]
    assert attempt["status"] == "unknown" and attempt["can_verify"]
    assert attempt["verification"] is None
    sent = copy.deepcopy(http.calls[0]["json"]["message"])
    sent.update(
        {
            "id": "sent-copy",
            "isDraft": False,
            "sentDateTime": datetime.now(timezone.utc).isoformat(),
            "webLink": "https://outlook.office.com/mail/sent-copy",
        }
    )
    with app.state.session_factory.begin() as db:
        saved = db.get(EmailAttempt, attempt["id"])
        assert sent["internetMessageHeaders"][0]["value"] == saved.correlation_id
        assert saved.correlation_id not in json.dumps(result)
    transport = SentHTTP(http, [sent])
    graph.session = transport
    return service, transport, sent, path, attempt


def test_verification_requires_personal_read_access_and_matches_the_exact_attempt(email_service):
    service, http, sent, path, attempt = uncertain_message(email_service)
    _, client, _, _, _, org, alice, bob = service
    verify = path + "/attempts/" + attempt["id"] + "/verify"
    assert client.post(verify, headers=alice[2], json={}).status_code == 404
    assert client.post(verify, headers=bob[2], json={}).status_code == 403
    assert not http.reads
    read_consent(service)
    mismatch = copy.deepcopy(sent)
    mismatch["toRecipients"] = [{"emailAddress": {"address": "other@example.com"}}]
    wrong_marker = copy.deepcopy(sent)
    wrong_marker["internetMessageHeaders"][0]["value"] = "another-attempt"
    duplicate_header = copy.deepcopy(sent)
    duplicate_header["internetMessageHeaders"] *= 2
    http.sent = [
        mismatch,
        wrong_marker,
        duplicate_header,
        {**sent, "isDraft": True},
        {**sent, "sentDateTime": "1999-01-01T00:00:00Z"},
    ]
    http.next_link = "https://outside.example/never-follow"
    absent = client.post(verify, headers=bob[2], json={}).json()
    assert absent["attempts"][-1]["verification"]["status"] == "not_found"
    assert absent["attempts"][-1]["verification"]["partial"]
    assert absent["attempts"][-1]["status"] == "unknown" and not absent["editable"]
    assert len(http.reads) == 1 and len(http.original.calls) == 1
    assert http.reads[0]["headers"]["Authorization"] == "Bearer synthetic-access-" + bob[1]
    assert (
        client.post(path + "/send", headers=bob[2], json={"version": 1, "confirmed": True}).status_code == 200
    )
    http.sent = [
        {
            **sent,
            "internetMessageHeaders": [
                {**sent["internetMessageHeaders"][0], "name": "X-AlpenData-Message-Id"}
            ],
        }
    ]
    found = client.post(verify, headers=bob[2], json={}).json()
    observation = found["attempts"][-1]["verification"]
    assert observation["status"] == "found" and observation["copy"]["item_id"] == "sent-copy"
    assert observation["copy"]["url"] == sent["webLink"]
    assert found["attempts"][-1]["status"] == "unknown" and not found["editable"]
    assert "delivered" not in json.dumps(found)
    http.sent = []
    assert client.post(verify, headers=bob[2], json={}).json() == found
    assert len(http.reads) == 2 and len(http.original.calls) == 1
    assert client.get(path, headers=bob[2]).json() == found


def test_missing_legacy_marker_and_company_restrictions_never_turn_into_non_delivery(email_service):
    service, http, _, path, attempt = uncertain_message(email_service)
    app, client, _, _, _, org, alice, bob = service
    verify = path + "/attempts/" + attempt["id"] + "/verify"
    read_consent(service)
    policy_path = f"/api/organizations/{org}/policy"
    policy = client.get(policy_path, headers=alice[2]).json()
    allowed = policy["allowed_capabilities"]
    assert (
        client.put(
            policy_path,
            headers=alice[2],
            json={
                "version": policy["version"],
                "allowed_capabilities": [item for item in allowed if item != "mail"],
            },
        ).status_code
        == 200
    )
    assert client.post(verify, headers=bob[2], json={}).json()["detail"] == "company_policy_denied"
    assert not http.reads
    policy = client.get(policy_path, headers=alice[2]).json()
    assert (
        client.put(
            policy_path,
            headers=alice[2],
            json={"version": policy["version"], "allowed_capabilities": allowed},
        ).status_code
        == 200
    )
    http.status = 429
    assert client.post(verify, headers=bob[2], json={}).status_code == 429
    current = client.get(path, headers=bob[2]).json()
    assert current["attempts"][-1]["verification"] is None
    with app.state.session_factory.begin() as db:
        db.get(EmailAttempt, attempt["id"]).correlation_id = None
    current = client.get(path, headers=bob[2]).json()
    assert not current["attempts"][-1]["can_verify"]
    assert client.post(verify, headers=bob[2], json={}).json()["detail"] == "email_verification_unavailable"
    assert not current["editable"] and current["attempts"][-1]["status"] == "unknown"
    assert len(http.reads) == 1 and len(http.original.calls) == 1
