from uuid import uuid4

from test_chat import join
from test_chat import service as service


def test_results_remain_private_and_read_markers_never_restart_work(service, account, verification):
    _, client = service
    _, owner = account("owner@example.com")
    _, peer = account("peer@example.com")
    org = client.post("/api/organizations", headers=owner, json={"name": "PME"}).json()["id"]
    root = f"/api/organizations/{org}"
    join(client, verification, root, owner, peer, "peer@example.com")
    client.put(
        root + "/onboarding", headers=owner, json={"language": "fr", "role": "Coach", "needs": "Meetings"}
    )
    conversation = client.post(root + "/chat/conversations", headers=owner, json={}).json()["id"]
    path = root + "/chat/conversations/" + conversation
    turn = client.post(
        path + "/turns", headers=owner, json={"request_id": str(uuid4()), "message": "Work"}
    ).json()
    assert client.get(root + "/work-inbox", headers=owner).json()["items"] == []
    client.post(path + "/turns/" + turn["id"] + "/cancel", headers=owner)
    inbox = client.get(root + "/work-inbox", headers=owner).json()
    assert inbox["unread"] == 1 and inbox["items"][0]["status"] == "cancelled"
    assert client.get(root + "/work-inbox", headers=peer).json()["items"] == []
    mark = root + "/work-inbox/" + turn["id"] + "/read"
    assert client.put(mark, headers=peer, json={}).status_code == 404
    for _ in range(2):
        assert client.put(mark, headers=owner, json={}).json() == {"read": True}
    assert client.get(root + "/work-inbox", headers=owner).json()["unread"] == 0
    assert client.get(path, headers=owner).json()["turns"][0]["status"] == "cancelled"
