def test_admin_cannot_access_colleague_resources_and_membership_is_checked_on_every_call(
    service, account, verification
):
    _, client = service
    admin_id, admin = account("admin@example.com")
    colleague_id, colleague = account("colleague@example.com")
    _, outsider = account("outsider@example.com")

    organization = client.post("/api/organizations", headers=admin, json={"name": "Company A"}).json()["id"]
    foreign = client.post("/api/organizations", headers=outsider, json={"name": "Company B"}).json()["id"]
    base = f"/api/organizations/{organization}"
    assert client.get(base, headers=outsider).status_code == 404
    assert client.get(base).status_code == 401
    assert client.get(base, headers={"X-User-Id": admin_id}).status_code == 401

    answers = {"language": "en", "role": "Manager", "needs": "Prepare meetings"}
    assert client.put(f"{base}/onboarding", headers=admin, json=answers).status_code == 200
    invite = client.post(f"{base}/invitations", headers=admin, json={"email": "colleague@example.com"})
    assert invite.status_code == 201
    token = invite.json()["token"]
    pending = client.get(f"{base}/invitations", headers=admin).json()["invitations"]
    assert pending == [
        {
            "id": invite.json()["id"],
            "email": "colleague@example.com",
            "expires_at": invite.json()["expires_at"],
        }
    ]
    assert client.get(f"{base}/invitations", headers=outsider).status_code == 404
    assert client.post("/api/invitations/accept", headers=outsider, json={"token": token}).status_code == 403
    proof = verification(colleague, token)
    assert (
        client.post(
            "/api/invitations/accept", headers=colleague, json={"token": token, "verification_token": proof}
        ).status_code
        == 200
    )
    assert client.post("/api/invitations/accept", headers=colleague, json={"token": token}).status_code == 404
    assert client.get(f"{base}/onboarding", headers=colleague).json() == {
        "language": "fr",
        "step": "introduction",
        "answers": {},
    }
    assert client.get(f"{base}/onboarding", headers=admin).json()["answers"]["role"] == "Manager"
    assert client.get(f"{base}/members", headers=colleague).status_code == 403
    assert client.get(f"{base}/invitations", headers=colleague).status_code == 403
    assert client.get(f"{base}/invitations", headers=admin).json()["invitations"] == []
    roster = client.get(f"{base}/members", headers=admin).json()["members"]
    assert any(item["user_id"] == colleague_id and item["display_name"] == "colleague" for item in roster)

    payload = {"kind": "memory", "title": "Private note", "content": "Synthetic private content"}
    response = client.post(f"{base}/personal-resources", headers=colleague, json=payload)
    assert response.status_code == 201
    resource = response.json()["id"]
    path = f"{base}/personal-resources/{resource}"
    assert client.get(path, headers=colleague).json()["content"] == payload["content"]
    assert client.get(path, headers=admin).status_code == 404
    assert client.delete(path, headers=admin).status_code == 404
    assert client.get(f"{base}/personal-resources", headers=admin).json() == {"resources": []}
    assert (
        client.get(
            f"/api/organizations/{foreign}/personal-resources/{resource}", headers=outsider
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"{base}/personal-resources",
            headers=admin,
            json={
                **payload,
                "owner_id": colleague_id,
            },
        ).status_code
        == 422
    )
    assert response.headers["Cache-Control"] == "no-store"

    changes = {"role": "member", "active": False, "licensed": True}
    assert client.patch(f"{base}/members/{colleague_id}", headers=admin, json=changes).status_code == 200
    assert client.get(path, headers=colleague).status_code == 404
    assert client.put(f"{base}/onboarding", headers=colleague, json=answers).status_code == 404
    assert client.patch(f"{base}/members/{admin_id}", headers=admin, json=changes).status_code == 409
    assert client.get(base, headers=admin).status_code == 200

    assert client.post("/api/logout", headers=admin).status_code == 204
    assert client.get(base, headers=admin).status_code == 401
