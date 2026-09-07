from uuid import uuid4

from test_chat import join
from test_chat import service as service


def test_personal_library_is_private_versioned_and_not_project_context(service, account, verification):
    _, client = service
    _, admin = account("admin@example.com")
    _, peer = account("peer@example.com")
    org = client.post("/api/organizations", headers=admin, json={"name": "PME"}).json()["id"]
    root = f"/api/organizations/{org}"
    join(client, verification, root, admin, peer, "peer@example.com")
    path = root + "/knowledge/" + str(uuid4())
    body = {"kind": "method", "title": "Meeting preparation", "content": "Ask for the agenda first."}
    assert client.put(path, headers=peer, json=body).status_code == 200
    assert client.put(path, headers=peer, json=body).json()["version"] == 1
    assert client.get(root + "/knowledge", headers=admin).json()["entries"] == []
    assert client.put(path, headers=admin, json=body).status_code == 404
    changed = {**body, "version": 1, "content": "Review the agenda and ask for missing information."}
    assert client.put(path, headers=peer, json=changed).json()["version"] == 2
    assert client.put(path, headers=peer, json={**body, "version": 1}).status_code == 409
    assert client.delete(path, headers=admin).status_code == 404
    assert client.delete(path, headers=peer).status_code == 204
    assert client.get(root + "/knowledge", headers=peer).json()["entries"] == []
