from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

pytestmark = pytest.mark.linux_only


def test_concurrent_invites_cannot_overbook_and_acceptance_cannot_be_replayed(service, account, request):
    if not request.config.getoption("--postgresql-bin"):
        pytest.skip("Use --postgresql-bin to exercise real PostgreSQL row locks")
    _, client = service
    _, admin = account("admin@example.test")
    _, invitee = account("reserved@example.test")
    organization = client.post("/api/organizations", headers=admin, json={"name": "Concurrency"}).json()["id"]
    url = f"/api/organizations/{organization}/invitations"
    reserved = client.post(url, headers=admin, json={"email": "reserved@example.test"}).json()["token"]
    barrier = Barrier(2)

    def invite(email):
        barrier.wait(timeout=10)
        return client.post(url, headers=admin, json={"email": email}).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(invite, ["first@example.test", "second@example.test"]))
    assert sorted(results) == [201, 409]

    barrier = Barrier(2)

    def accept(_):
        barrier.wait(timeout=10)
        return client.post("/api/invitations/accept", headers=invitee, json={"token": reserved}).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(accept, range(2)))
    assert sorted(results) == [200, 404]
    members = client.get(f"/api/organizations/{organization}/members", headers=admin).json()["members"]
    assert len({member["user_id"] for member in members}) == len(members) == 2
