from uuid import uuid4

from sqlalchemy import select
from test_chat import join
from test_chat import service as service

from alpendata_api.conversation_branches import branch_history
from alpendata_api.models import ChatTurn, Conversation, now


def test_branch_preserves_history_and_never_replays_actions(service, account, verification):
    app, client = service
    _, admin = account("admin@example.com")
    _, peer = account("peer@example.com")
    org = client.post("/api/organizations", headers=admin, json={"name": "PME"}).json()["id"]
    base = f"/api/organizations/{org}"
    join(client, verification, base, admin, peer, "peer@example.com")
    client.put(
        base + "/onboarding", headers=peer, json={"language": "fr", "role": "Coach", "needs": "Meetings"}
    )
    root = base + "/chat"
    source = client.post(root + "/conversations", headers=peer, json={}).json()
    path = root + "/conversations/" + source["id"]
    turn = client.post(
        path + "/turns", headers=peer, json={"request_id": str(uuid4()), "message": "Send the appointment"}
    ).json()
    with app.state.session_factory.begin() as db:
        row = db.get(ChatTurn, turn["id"])
        row.status, row.response, row.finished_at = "completed", "Appointment accepted", now()
    payload = {"request_id": str(uuid4()), "through_sequence": 1}
    assert client.post(path + "/branches", headers=admin, json=payload).status_code == 404
    created = client.post(path + "/branches", headers=peer, json=payload)
    assert created.status_code == 201, created.text
    assert client.post(path + "/branches", headers=peer, json=payload).json() == created.json()
    branch_id = created.json()["id"]
    with app.state.session_factory() as db:
        target = db.get(Conversation, branch_id)
        assert branch_history(db, target) == [
            {"role": "user", "content": "Send the appointment"},
            {"role": "assistant", "content": "Appointment accepted"},
        ]
        assert db.scalar(select(ChatTurn).where(ChatTurn.conversation_id == branch_id)).status == "completed"
        assert db.get(ChatTurn, turn["id"]).conversation_id == source["id"]
    copied = client.get(root + "/conversations/" + branch_id, headers=peer).json()["turns"][0]
    assert copied["emails"] == [] and copied["artifacts"] == []
    assert client.get(path + "/export", headers=admin).status_code == 404
    assert "Appointment accepted" in client.get(path + "/export", headers=peer).text


def test_search_finds_private_content_and_favorites_survive_legacy_updates(service, account):
    _, client = service
    _, owner = account("owner@example.com")
    _, outsider = account("outsider@example.com")
    org = client.post("/api/organizations", headers=owner, json={"name": "PME"}).json()["id"]
    base = f"/api/organizations/{org}"
    client.put(
        base + "/onboarding", headers=owner, json={"language": "fr", "role": "Coach", "needs": "Meetings"}
    )
    root = base + "/chat"
    item = client.post(root + "/conversations", headers=owner, json={"title": "Client"}).json()
    path = root + "/conversations/" + item["id"]
    client.post(
        path + "/turns", headers=owner, json={"request_id": str(uuid4()), "message": "Confidential amethyst"}
    )
    assert len(client.get(root + "?q=amethyst", headers=owner).json()["conversations"]) == 1
    match = client.get(root + "?q=amethyst", headers=owner).json()["conversations"][0]["match"]
    assert match["text"] == "Confidential amethyst" and match["sequence"] == 1
    assert client.get(root + "?q=amethyst", headers=outsider).status_code == 404
    assert client.get(root + "?q=%25", headers=owner).json()["conversations"] == []
    assert client.put(path, headers=owner, json={"title": "Client", "pinned": True}).json()["pinned"]
    assert client.put(path, headers=owner, json={"title": "Renamed"}).json()["pinned"]
