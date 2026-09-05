from alpendata_api.models import Invitation, now


def test_invitations_reserve_seats_expire_and_never_assign_roles_from_client_data(service, account):
    app, client = service
    _, admin = account("admin@example.test")
    _, second = account("second@example.test")
    _, third = account("third@example.test")
    organization = client.post("/api/organizations", headers=admin, json={"name": "Coaching"}).json()["id"]
    base = f"/api/organizations/{organization}"

    def invite(email, **extras):
        return client.post(f"{base}/invitations", headers=admin, json={"email": email, **extras})

    assert invite("second@example.test", role="admin").status_code == 422
    invitation = invite("second@example.test").json()
    assert invite("SECOND@example.test").status_code == 409
    third_invitation = invite("third@example.test").json()
    assert invite("fourth@example.test").status_code == 409

    with app.state.session_factory.begin() as db:
        record = db.get(Invitation, invitation["id"])
        assert record.token_hash != invitation["token"]
        record.expires_at = now() - 1
    assert (
        client.post(
            "/api/invitations/accept",
            headers=second,
            json={
                "token": invitation["token"],
            },
        ).status_code
        == 404
    )

    renewed = invite("second@example.test")
    assert renewed.status_code == 201
    assert client.delete(f"{base}/invitations/{third_invitation['id']}", headers=admin).status_code == 204
    assert (
        client.post(
            "/api/invitations/accept",
            headers=third,
            json={
                "token": third_invitation["token"],
            },
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/invitations/accept",
            headers=second,
            json={
                "token": renewed.json()["token"],
            },
        ).status_code
        == 200
    )
    second_id = client.get("/api/me", headers=second).json()["id"]
    assert client.get("/api/me", headers=second).json()["memberships"][0]["role"] == "member"
    assert (
        client.patch(
            f"{base}/members/{second_id}",
            headers=second,
            json={
                "role": "admin",
                "active": True,
                "licensed": True,
            },
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"{base}/members/{second_id}",
            headers=admin,
            json={
                "role": "member",
                "active": True,
                "licensed": False,
            },
        ).status_code
        == 200
    )
    assert client.get(f"{base}/onboarding", headers=second).status_code == 403
    assert client.get(base, headers=second).status_code == 200
