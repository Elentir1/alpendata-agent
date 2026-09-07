from uuid import uuid4

import pytest
from test_chat import join
from test_chat import service as service

from alpendata_api.chat_worker import ChatWorker
from alpendata_api.runtime import RuntimeFailure


def test_revocation_stops_existing_project_work_and_prevents_new_model_access(service, account, verification):
    app, client = service
    _, owner = account("owner@example.com")
    peer_id, peer = account("peer@example.com")
    org = client.post("/api/organizations", headers=owner, json={"name": "PME"}).json()["id"]
    root = f"/api/organizations/{org}"
    join(client, verification, root, owner, peer, "peer@example.com")
    client.put(
        root + "/onboarding", headers=peer, json={"language": "en", "role": "Coach", "needs": "Projects"}
    )
    project = client.post(
        root + "/chat/projects", headers=owner, json={"name": "Client", "instructions": "Client-only context"}
    ).json()["id"]
    access = root + "/chat/projects/" + project + "/members"
    assert client.put(access, headers=owner, json={"user_id": peer_id}).status_code == 200
    chat = client.post(root + "/chat/conversations", headers=peer, json={"project_id": project}).json()["id"]
    path = root + "/chat/conversations/" + chat
    assert (
        client.post(
            path + "/turns",
            headers=peer,
            json={"request_id": str(uuid4()), "message": "Review the client context"},
        ).status_code
        == 202
    )
    worker = ChatWorker(app.state.chat_settings, app.state.session_factory, runtime=object())
    job = worker.claim()
    assert client.delete(access + "/" + peer_id, headers=owner).status_code == 204
    with pytest.raises(RuntimeFailure, match="project_context_revoked"):
        worker.model(job, {})
    worker.finish(job, result={"response": "This late response must not be published"})
    result = client.get(path, headers=peer).json()["turns"][0]
    assert result["response"] is None and result["error_code"] == "project_context_revoked"
    assert (
        client.post(
            path + "/turns", headers=peer, json={"request_id": str(uuid4()), "message": "Continue"}
        ).status_code
        == 403
    )


def test_project_sharing_keeps_conversations_private_and_revokes_resource_reads(
    service, account, verification
):
    _, client = service
    owner_id, owner = account("owner@example.com")
    peer_id, peer = account("peer@example.com")
    org = client.post("/api/organizations", headers=owner, json={"name": "PME"}).json()["id"]
    base = f"/api/organizations/{org}"
    join(client, verification, base, owner, peer, "peer@example.com")
    for headers in (owner, peer):
        client.put(
            base + "/onboarding",
            headers=headers,
            json={"language": "fr", "role": "Coach", "needs": "Meetings"},
        )
    root = base + "/chat"
    project = client.post(root + "/projects", headers=peer, json={"name": "Client"}).json()
    path = root + "/projects/" + project["id"]
    assert client.get(path + "/entries", headers=owner).status_code == 404
    assert (
        client.put(path + "/members", headers=peer, json={"user_id": owner_id, "role": "reader"}).status_code
        == 200
    )
    assert client.get(root + "/projects", headers=owner).json()["projects"][0]["role"] == "reader"
    entry = {
        "request_id": str(uuid4()),
        "title": "Project knowledge",
        "content": "Shared source",
        "kind": "method",
    }
    assert client.post(path + "/entries", headers=owner, json=entry).status_code == 403
    assert client.post(path + "/entries", headers=peer, json=entry).status_code == 201
    assert client.post(path + "/entries", headers=peer, json=entry).status_code == 201
    assert len(client.get(path + "/entries", headers=owner).json()["entries"]) == 1
    assert (
        client.post(path + "/entries", headers=peer, json={**entry, "content": "Changed"}).status_code == 409
    )
    assert client.get(path + "/entries", headers=owner).json()["entries"][0]["content"] == "Shared source"
    conversation = client.post(
        root + "/conversations", headers=owner, json={"project_id": project["id"]}
    ).json()
    private = root + "/conversations/" + conversation["id"]
    assert client.get(private, headers=peer).status_code == 404
    assert client.get(root + "?project=" + project["id"], headers=peer).json()["conversations"] == []
    assert client.delete(path + "/members/" + owner_id, headers=peer).status_code == 204
    assert client.get(path + "/entries", headers=owner).status_code == 404
    assert client.get(private, headers=owner).status_code == 200


def test_parallel_conversations_have_distinct_jobs_and_private_resumable_events(service, account):
    app, client = service
    _, owner = account("owner@example.com")
    _, outsider = account("outsider@example.com")
    org = client.post("/api/organizations", headers=owner, json={"name": "PME"}).json()["id"]
    base = f"/api/organizations/{org}"
    client.put(
        base + "/onboarding", headers=owner, json={"language": "fr", "role": "Coach", "needs": "Meetings"}
    )
    worker = ChatWorker(app.state.chat_settings, app.state.session_factory, runtime=object())
    conversations = []
    for _ in range(4):
        conversation = client.post(base + "/chat/conversations", headers=owner, json={}).json()
        path = base + "/chat/conversations/" + conversation["id"]
        conversations.append(path)
        assert (
            client.post(
                path + "/turns", headers=owner, json={"request_id": str(uuid4()), "message": "Work"}
            ).status_code
            == 202
        )
    jobs = [worker.claim() for _ in range(3)]
    assert len({job.id for job in jobs}) == 3
    assert worker.claim() is None
    events = client.get(conversations[0] + "/events", headers=owner).json()
    assert events["events"][0]["kind"] == "queued"
    cursor = events["next_after"]
    assert client.get(conversations[0] + f"/events?after={cursor}", headers=owner).json()["events"] == []
    assert client.get(conversations[0] + "/events", headers=outsider).status_code == 404
    assert (
        worker.activity(jobs[0], {"kind": "tool_started", "label": "terminal", "arguments": "secret"})[
            "status"
        ]
        == 400
    )
    worker.finish(jobs[0], error="agent_cancelled")
    assert worker.claim() is not None
