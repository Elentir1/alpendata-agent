from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from email import policy
from email.parser import BytesParser
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
from test_smtp_delivery import smtp_server as smtp_server

from alpendata_api.models import Invitation, now


@pytest.fixture
def service(database_url, service_factory, smtp_server):
    settings, mailer, _ = smtp_server
    with service_factory(replace(settings, database_url=database_url), mailer=mailer) as pair:
        yield pair


def link(inbox, index):
    message = BytesParser(policy=policy.default).parsebytes(inbox.messages[index][2])
    url = next(line for line in message.get_content().splitlines() if line.startswith("https://"))
    return parse_qs(urlsplit(url).fragment)


def test_email_invitation_commits_once_and_requires_personal_proof(service, account, smtp_server, request):
    app, client = service
    _, _, inbox = smtp_server
    _, admin = account("admin@example.com")
    _, colleague = account("colleague@example.com")
    _, outsider = account("outsider@example.com")
    org = client.post("/api/organizations", headers=admin, json={"name": "Coaches"}).json()["id"]
    base = f"/api/organizations/{org}"
    body = {"email": "colleague@example.com", "request_id": str(uuid4()), "language": "en"}
    if request.config.getoption("--postgresql-bin"):
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(
                pool.map(
                    lambda _: client.post(base + "/invitations/email", headers=admin, json=body), range(2)
                )
            )
        assert all(response.status_code == 201 for response in responses)
    else:
        assert client.post(base + "/invitations/email", headers=admin, json=body).status_code == 201
    receipt = client.post(base + "/invitations/email", headers=admin, json=body).json()
    assert receipt["delivery_status"] == "submitted"
    assert "token" not in receipt and len(inbox.messages) == 1
    assert inbox.messages[0][1] == ["colleague@example.com"]
    invitation = link(inbox, 0)
    assert set(invitation) == {"invitation"}
    token = invitation["invitation"][0]
    with app.state.session_factory() as db:
        assert db.get(Invitation, receipt["id"]).token_hash != token
    assert client.post(base + "/invitations/email", headers=outsider, json=body).status_code == 404
    assert (
        client.post(base + "/invitations/email", headers=admin, json={**body, "language": "fr"}).status_code
        == 409
    )
    assert client.post("/api/invitations/accept", headers=colleague, json={"token": token}).status_code == 403
    assert (
        client.post(
            "/api/invitations/verify", headers=colleague, json={"token": token, "language": "en"}
        ).status_code
        == 202
    )
    proof = link(inbox, 1)["verification"][0]
    assert (
        client.post(
            "/api/invitations/accept", headers=outsider, json={"token": token, "verification_token": proof}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/invitations/accept", headers=colleague, json={"token": token, "verification_token": proof}
        ).status_code
        == 200
    )
    assert client.post(base + "/invitations/email", headers=admin, json=body).json()["accepted"]
    assert len(inbox.messages) == 2
    assert client.get(base + "/invitations", headers=admin).json()["invitations"] == []


def test_uncertain_smtp_delivery_is_retained_and_never_replayed(database_url, service_factory, smtp_server):
    from alpendata_api.auth import issue_session
    from alpendata_api.models import User

    settings, mailer, inbox = smtp_server

    class LostAcknowledgement:
        def send(self, message):
            mailer.send(message)
            raise TimeoutError("private SMTP response")

    with service_factory(replace(settings, database_url=database_url), mailer=LostAcknowledgement()) as (
        app,
        client,
    ):
        with app.state.session_factory.begin() as db:
            user = User(
                issuer="test", subject="admin", verified_email="admin@example.com", display_name="Admin"
            )
            db.add(user)
            db.flush()
            headers = {"Authorization": "Bearer " + issue_session(db, user, 3600)}
        org = client.post("/api/organizations", headers=headers, json={"name": "Coaches"}).json()["id"]
        base = f"/api/organizations/{org}"
        body = {"email": "coach@example.com", "request_id": str(uuid4()), "language": "fr"}
        response = client.post(base + "/invitations/email", headers=headers, json=body)
        receipt = response.json()
        assert response.status_code == 201 and receipt["delivery_status"] == "unknown"
        assert "private SMTP response" not in response.text
        assert client.post(base + "/invitations/email", headers=headers, json=body).json() == receipt
        assert (
            client.post(
                base + "/invitations/email", headers=headers, json={**body, "request_id": str(uuid4())}
            ).status_code
            == 409
        )
        with app.state.session_factory.begin() as db:
            item = db.get(Invitation, receipt["id"])
            item.delivery_status, item.delivery_started_at = "sending", now() - 121
        assert (
            client.get(base + "/invitations", headers=headers).json()["invitations"][0]["delivery_status"]
            == "unknown"
        )
        assert (
            client.post(base + "/invitations/email", headers=headers, json=body).json()["delivery_status"]
            == "unknown"
        )
        assert client.delete(base + "/invitations/" + receipt["id"], headers=headers).status_code == 204
        assert client.post(base + "/invitations/email", headers=headers, json=body).json()["revoked"]
        assert (
            client.post(
                "/api/invitations/verify",
                headers=headers,
                json={"token": link(inbox, 0)["invitation"][0], "language": "fr"},
            ).status_code
            == 404
        )
        assert len(inbox.messages) == 1
        with app.state.session_factory.begin() as db:
            for _ in range(19):
                identifier = str(uuid4())
                db.add(
                    Invitation(
                        id=identifier,
                        organization_id=org,
                        inviter_id=user.id,
                        recipient_email="prior@example.com",
                        token_hash=uuid4().hex * 2,
                        expires_at=now() + 3600,
                        revoked=True,
                        delivery_request_id=identifier,
                        delivery_status="submitted",
                        delivery_started_at=now(),
                        delivery_language="fr",
                    )
                )
        limited = client.post(
            base + "/invitations/email", headers=headers, json={**body, "request_id": str(uuid4())}
        )
        assert limited.status_code == 429
        assert limited.json()["detail"] == "invitation_rate_limited"
        assert len(inbox.messages) == 1
