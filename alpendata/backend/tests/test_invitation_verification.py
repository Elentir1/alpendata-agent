from urllib.parse import parse_qs, urlsplit

from sqlalchemy import select
from test_microsoft_signin import begin
from test_microsoft_signin import signin_service as signin_service

from alpendata_api.auth import issue_session
from alpendata_api.models import InvitationProof, User, now


def test_microsoft_user_joins_only_with_fresh_mailbox_proof_bound_to_their_account(
    signin_service, mail_outbox
):
    app, client, settings, server = signin_service
    with app.state.session_factory.begin() as db:
        admin = User(issuer="synthetic", subject="admin", display_name="Administrator")
        db.add(admin)
        db.flush()
        admin_headers = {"Authorization": "Bearer " + issue_session(db, admin, 3600)}
    organization = client.post("/api/organizations", headers=admin_headers, json={"name": "Coaches"}).json()[
        "id"
    ]
    invitation = client.post(
        f"/api/organizations/{organization}/invitations",
        headers=admin_headers,
        json={"email": "coach@example.com"},
    ).json()["token"]
    callback = begin(client, settings, server)
    assert (
        client.post("/api/auth/microsoft/callback", data=callback, follow_redirects=False).status_code == 303
    )
    user_id = client.get("/api/me").json()["id"]
    origin = {"Origin": settings.public_origin}
    assert (
        client.post("/api/invitations/accept", headers=origin, json={"token": invitation}).status_code == 403
    )
    response = client.post(
        "/api/invitations/verify", headers=origin, json={"token": invitation, "language": "en"}
    )
    assert response.status_code == 202
    assert mail_outbox[-1]["To"] == "coach@example.com"
    assert mail_outbox[-1]["Subject"] == "Confirm your AlpenData invitation"
    link = next(line for line in mail_outbox[-1].get_content().splitlines() if line.startswith("https://"))
    proof = parse_qs(urlsplit(link).fragment)["verification"][0]
    assert proof not in response.text and not urlsplit(link).query
    assert (
        client.post("/api/invitations/verify", headers=origin, json={"token": invitation}).status_code == 429
    )
    assert len(mail_outbox) == 1
    body = {"token": invitation, "verification_token": proof}
    # Even someone holding both tokens cannot substitute the initiating account.
    assert client.post("/api/invitations/accept", headers=admin_headers, json=body).status_code == 403
    other_company = client.post(
        "/api/organizations", headers=admin_headers, json={"name": "Other company"}
    ).json()["id"]
    other_invitation = client.post(
        f"/api/organizations/{other_company}/invitations",
        headers=admin_headers,
        json={"email": "coach@example.com"},
    ).json()["token"]
    assert (
        client.post(
            "/api/invitations/accept",
            headers=origin,
            json={"token": other_invitation, "verification_token": proof},
        ).status_code
        == 403
    )
    with app.state.session_factory.begin() as db:
        record = db.scalar(select(InvitationProof).where(InvitationProof.user_id == user_id))
        assert record.token_hash != proof
        record.expires_at = now() - 1
    assert client.post("/api/invitations/accept", headers=origin, json=body).status_code == 403
    with app.state.session_factory.begin() as db:
        record = db.scalar(select(InvitationProof).where(InvitationProof.user_id == user_id))
        record.created_at = now() - 61
    assert (
        client.post("/api/invitations/verify", headers=origin, json={"token": invitation}).status_code == 202
    )
    link = next(line for line in mail_outbox[-1].get_content().splitlines() if line.startswith("https://"))
    body["verification_token"] = parse_qs(urlsplit(link).fragment)["verification"][0]
    assert client.post("/api/invitations/accept", headers=origin, json=body).status_code == 200
    assert client.post("/api/invitations/accept", headers=origin, json=body).status_code == 404
    assert client.get(f"/api/organizations/{organization}/onboarding").json()["answers"] == {}
    assert client.get(f"/api/organizations/{organization}/personal-resources").json() == {"resources": []}


def test_uncertain_delivery_rolls_back_proof_and_cannot_grant_membership(database_url, service_factory):
    class UncertainMailer:
        def send(self, message):
            self.message = message
            raise OSError("Synthetic connection loss after DATA")

    mailer = UncertainMailer()
    with service_factory(mailer=mailer) as (app, client):
        with app.state.session_factory.begin() as db:
            admin = User(issuer="synthetic", subject="admin", display_name="Admin")
            colleague = User(issuer="synthetic", subject="coach", display_name="Coach")
            db.add_all([admin, colleague])
            db.flush()
            admin_headers = {"Authorization": "Bearer " + issue_session(db, admin, 3600)}
            colleague_headers = {"Authorization": "Bearer " + issue_session(db, colleague, 3600)}
        organization = client.post(
            "/api/organizations", headers=admin_headers, json={"name": "Coaches"}
        ).json()["id"]
        invitation = client.post(
            f"/api/organizations/{organization}/invitations",
            headers=admin_headers,
            json={"email": "coach@example.com"},
        ).json()["token"]
        assert (
            client.post(
                "/api/invitations/verify", headers=colleague_headers, json={"token": invitation}
            ).status_code
            == 502
        )
        link = next(line for line in mailer.message.get_content().splitlines() if line.startswith("https://"))
        proof = parse_qs(urlsplit(link).fragment)["verification"][0]
        with app.state.session_factory() as db:
            assert db.scalars(select(InvitationProof)).all() == []
        assert (
            client.post(
                "/api/invitations/accept",
                headers=colleague_headers,
                json={"token": invitation, "verification_token": proof},
            ).status_code
            == 403
        )
