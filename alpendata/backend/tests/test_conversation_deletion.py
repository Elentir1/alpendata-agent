import base64
from uuid import uuid4

import pytest
from test_chat import join
from test_chat import service as service
from test_documents import example_pdf

from alpendata_api.chat_worker import ChatWorker
from alpendata_api.runtime import RuntimeFailure


def test_deletion_stops_work_revokes_direct_links_and_preserves_published_copies(
    service, account, verification
):
    app, client = service
    _, owner = account("owner@example.com")
    peer_id, peer = account("peer@example.com")
    org = client.post("/api/organizations", headers=owner, json={"name": "PME"}).json()["id"]
    root = f"/api/organizations/{org}"
    join(client, verification, root, owner, peer, "peer@example.com")
    client.put(
        root + "/onboarding", headers=owner, json={"language": "en", "role": "Coach", "needs": "Documents"}
    )
    chat = client.post(root + "/chat/conversations", headers=owner, json={}).json()["id"]
    path = root + "/chat/conversations/" + chat
    file = client.post(
        path + "/files",
        headers=owner,
        json={
            "request_id": str(uuid4()),
            "filename": "notes.txt",
            "content_base64": base64.b64encode(b"Private notes").decode(),
        },
    ).json()
    project = client.post(root + "/chat/projects", headers=owner, json={"name": "Shared"}).json()["id"]
    project_path = root + "/chat/projects/" + project
    client.put(project_path + "/members", headers=owner, json={"user_id": peer_id})
    published = client.post(
        project_path + "/files",
        headers=owner,
        json={"request_id": str(uuid4()), "file_id": file["id"], "version": 1},
    ).json()
    branch = client.post(
        path + "/branches", headers=owner, json={"request_id": str(uuid4()), "through_sequence": 0}
    ).json()["id"]
    client.post(
        path + "/turns", headers=owner, json={"request_id": str(uuid4()), "message": "Prepare a document"}
    )
    worker = ChatWorker(app.state.chat_settings, app.state.session_factory, runtime=object())
    job = worker.claim()
    artifact = worker.tool(
        job,
        [],
        {
            "kind": "document",
            "filename": "plan.pdf",
            "content_base64": base64.b64encode(example_pdf()).decode(),
        },
    )["body"]
    assert client.delete(path, headers=peer).status_code == 404
    assert client.delete(path, headers=owner).status_code == 204
    assert client.delete(path, headers=owner).status_code == 204
    with pytest.raises(RuntimeFailure, match="agent_cancelled"):
        worker.model(job, {})
    worker.finish(job, result={"response": "Late output"})
    for suffix in ("", "/export", "/files", "/events"):
        assert client.get(path + suffix, headers=owner).status_code == 404
    assert (
        client.post(
            path + "/turns", headers=owner, json={"request_id": str(uuid4()), "message": "Continue"}
        ).status_code
        == 404
    )
    assert client.get(root + "/files/" + file["id"] + "/versions/1/content", headers=owner).status_code == 404
    assert client.get(root + "/documents/" + artifact["id"] + "/download", headers=owner).status_code == 404
    assert chat not in str(client.get(root + "/chat?archived=true", headers=owner).json())
    assert client.get(root + "/work-inbox", headers=owner).json()["items"] == []
    assert client.get(root + "/chat/conversations/" + branch, headers=owner).status_code == 200
    assert (
        client.get(root + "/files/" + published["id"] + "/versions/1/content", headers=peer).text
        == "Private notes"
    )
