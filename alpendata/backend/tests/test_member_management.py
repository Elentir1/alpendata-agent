from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest


def join(client, verification, base, email, headers):
    token = client.post(base + "/invitations", headers=headers[0], json={"email": email}).json()["token"]
    response = client.post(
        "/api/invitations/accept",
        headers=headers[1],
        json={"token": token, "verification_token": verification(headers[1], token)},
    )
    assert response.status_code == 200


def test_roster_reports_reservations_and_versioned_changes_preserve_administration(
    service, account, verification
):
    _, client = service
    admin_id, admin = account("admin@example.com")
    coach_id, coach = account("coach@example.com")
    _, outsider = account("outside@example.com")
    org = client.post("/api/organizations", headers=admin, json={"name": "Coaching"}).json()["id"]
    base = f"/api/organizations/{org}"
    join(client, verification, base, "coach@example.com", (admin, coach))
    invitation = client.post(base + "/invitations", headers=admin, json={"email": "next@example.com"}).json()
    assert client.get(base + "/members", headers=coach).status_code == 403
    assert client.get(base + "/members", headers=outsider).status_code == 404
    roster = client.get(base + "/members", headers=admin).json()
    assert roster["seats"] == {"capacity": 3, "assigned": 2, "reserved": 1, "available": 0}
    current = next(m for m in roster["members"] if m["user_id"] == coach_id)
    payload = {"version": current["version"], "role": "member", "active": True, "licensed": False}
    path = base + "/members/" + coach_id
    assert (
        client.patch(
            path, headers=admin, json={k: v for k, v in payload.items() if k != "version"}
        ).status_code
        == 422
    )
    changed = client.patch(path, headers=admin, json=payload)
    assert changed.status_code == 200
    assert changed.json()["version"] > current["version"]
    assert client.patch(path, headers=admin, json=payload).json()["detail"] == "member_state_changed"
    assert client.get(base + "/members", headers=admin).json()["seats"]["available"] == 1
    promoted = client.patch(
        path, headers=admin, json={**payload, "version": changed.json()["version"], "role": "admin"}
    )
    assert promoted.status_code == 200
    # An active administrator can manage seats without consuming one themselves.
    assert client.get(base + "/members", headers=coach).status_code == 200
    original = next(m for m in roster["members"] if m["user_id"] == admin_id)
    demoted = client.patch(
        base + "/members/" + admin_id,
        headers=coach,
        json={"version": original["version"], "role": "member", "active": True, "licensed": True},
    )
    assert demoted.status_code == 200
    assert client.get(base + "/members", headers=admin).status_code == 403
    last = {**payload, "version": promoted.json()["version"], "role": "admin", "active": False}
    assert client.patch(path, headers=coach, json=last).json()["detail"] == "last_administrator"
    assert client.delete(base + "/invitations/" + invitation["id"], headers=coach).status_code == 204
    assert client.get(base + "/members", headers=coach).json()["seats"] == {
        "capacity": 3,
        "assigned": 1,
        "reserved": 0,
        "available": 2,
    }


@pytest.mark.linux_only
def test_concurrent_member_edits_and_reserved_seats_have_one_authoritative_winner(
    service, account, verification, request
):
    if not request.config.getoption("--postgresql-bin"):
        pytest.skip("Requires actual PostgreSQL locks")
    _, client = service
    _, admin = account("admin@example.com")
    first_id, first = account("first@example.com")
    second_id, second = account("second@example.com")
    org = client.post("/api/organizations", headers=admin, json={"name": "Concurrent coaching"}).json()["id"]
    base = f"/api/organizations/{org}"
    for uid, email, headers in [
        (first_id, "first@example.com", first),
        (second_id, "second@example.com", second),
    ]:
        join(client, verification, base, email, (admin, headers))
        assert (
            client.patch(
                base + "/members/" + uid,
                headers=admin,
                json={"version": 1, "role": "member", "active": True, "licensed": False},
            ).status_code
            == 200
        )

    def concurrent(changes):
        barrier = Barrier(2)

        def send(change):
            uid, body = change
            barrier.wait(timeout=15)
            return client.patch(base + "/members/" + uid, headers=admin, json=body)

        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(send, changes))

    original = {"version": 2, "role": "member", "active": True, "licensed": False}
    results = concurrent(
        [(first_id, {**original, "role": "admin"}), (first_id, {**original, "active": False})]
    )
    assert sorted(r.status_code for r in results) == [200, 409]
    assert next(r for r in results if r.status_code == 409).json()["detail"] == "member_state_changed"
    winner = next(r for r in results if r.status_code == 200).json()
    reset = client.patch(
        base + "/members/" + first_id, headers=admin, json={**original, "version": winner["version"]}
    ).json()
    assert (
        client.post(base + "/invitations", headers=admin, json={"email": "reserved@example.com"}).status_code
        == 201
    )
    results = concurrent(
        [
            (first_id, {**original, "version": reset["version"], "licensed": True}),
            (second_id, {**original, "licensed": True}),
        ]
    )
    assert sorted(r.status_code for r in results) == [200, 409]
    assert next(r for r in results if r.status_code == 409).json()["detail"] == "no_available_license"
    assert client.get(base + "/members", headers=admin).json()["seats"] == {
        "capacity": 3,
        "assigned": 2,
        "reserved": 1,
        "available": 0,
    }
