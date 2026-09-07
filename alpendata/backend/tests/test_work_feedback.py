from uuid import uuid4

from sqlalchemy import select
from test_chat import join
from test_chat import service as service

from alpendata_api.chat_worker import ChatWorker
from alpendata_api.models import Onboarding, now


def test_optional_feedback_aggregates_do_not_disclose_private_work_or_count_branches_twice(
    service, account, verification
):
    app, client = service
    _, admin = account("admin@example.com")
    peer_id, peer = account("peer@example.com")
    org = client.post("/api/organizations", headers=admin, json={"name": "PME"}).json()["id"]
    root = f"/api/organizations/{org}"
    join(client, verification, root, admin, peer, "peer@example.com")
    client.put(
        root + "/onboarding", headers=peer, json={"language": "en", "role": "Coach", "needs": "Meetings"}
    )
    with app.state.session_factory.begin() as db:
        profile = db.scalar(
            select(Onboarding).where(Onboarding.owner_id == peer_id, Onboarding.organization_id == org)
        )
        profile.started_at = now() - 60
    chat = client.post(root + "/chat/conversations", headers=peer, json={}).json()["id"]
    path = root + "/chat/conversations/" + chat
    turn = client.post(
        path + "/turns",
        headers=peer,
        json={"request_id": str(uuid4()), "message": "Private confidential request"},
    ).json()
    feedback = path + "/turns/" + turn["id"] + "/feedback"
    assert client.put(feedback, headers=peer, json={"outcome": "useful"}).status_code == 409
    worker = ChatWorker(app.state.chat_settings, app.state.session_factory, runtime=object())
    worker.finish(worker.claim(), result={"response": "Private confidential answer"})
    assert client.put(feedback, headers=admin, json={"outcome": "useful"}).status_code == 404
    assert client.put(feedback, headers=peer, json={"outcome": "useful"}).json()["outcome"] == "useful"
    assert client.put(feedback, headers=peer, json={"outcome": "useful"}).status_code == 200
    detail = client.get(path, headers=peer).json()["turns"][0]
    assert detail["feedback"] == "useful" and detail["feedback_available"]
    branch = client.post(
        path + "/branches", headers=peer, json={"request_id": str(uuid4()), "through_sequence": 1}
    ).json()["id"]
    copied = client.get(root + "/chat/conversations/" + branch, headers=peer).json()["turns"][0]
    assert not copied["feedback_available"]
    assert client.get(root + "/work-metrics", headers=peer).status_code == 403
    metrics = client.get(root + "/work-metrics", headers=admin)
    assert metrics.json()["executions"] == {"completed": 1}
    assert metrics.json()["feedback"] == {"useful": 1} and metrics.json()["first_useful_sample_size"] == 1
    assert 60 <= metrics.json()["first_useful_median_seconds"] <= 90
    assert "Private" not in metrics.text and peer_id not in metrics.text and chat not in metrics.text
    assert client.put(feedback, headers=peer, json={"outcome": "needs_changes"}).status_code == 200
    assert client.get(root + "/work-metrics", headers=admin).json()["feedback"] == {"needs_changes": 1}
    client.delete(path, headers=peer)
    assert client.put(feedback, headers=peer, json={"outcome": "useful"}).status_code == 404
