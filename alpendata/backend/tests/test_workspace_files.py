import base64
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from test_chat import join
from test_chat import service as service

from alpendata_api.file_store import FileStore, FileStoreSettings


def upload(text, **extra):
    return {"filename": "notes.txt", "content_base64": base64.b64encode(text.encode()).decode(), **extra}


def test_versions_preserve_history_reject_stale_writes_and_revoke_reads(service, account, verification):
    _, client = service
    owner_id, owner = account("owner@example.com")
    peer_id, peer = account("peer@example.com")
    org = client.post("/api/organizations", headers=owner, json={"name": "PME"}).json()["id"]
    root = f"/api/organizations/{org}"
    join(client, verification, root, owner, peer, "peer@example.com")
    client.put(
        root + "/onboarding", headers=peer, json={"language": "fr", "role": "Coach", "needs": "Documents"}
    )
    conv = client.post(root + "/chat/conversations", headers=peer, json={}).json()["id"]
    path = root + "/chat/conversations/" + conv + "/files"
    body = upload("original", request_id=str(uuid4()))
    first = client.post(path, headers=peer, json=body)
    assert first.status_code == 201
    item = first.json()
    assert client.post(path, headers=peer, json=body).json()["id"] == item["id"]
    file = root + "/files/" + item["id"]
    assert client.get(file + "/versions", headers=owner).status_code == 404
    assert (
        client.post(file + "/versions", headers=peer, json=upload("edited", expected_version=1)).status_code
        == 201
    )
    assert (
        client.post(file + "/versions", headers=peer, json=upload("stale", expected_version=1)).status_code
        == 409
    )
    assert client.get(file + "/versions/1/content", headers=peer).text == "original"
    assert client.get(file + "/versions/2/content", headers=peer).text == "edited"
    restored = client.post(file + "/restore", headers=peer, json={"expected_version": 2, "source_version": 1})
    assert restored.json()["version"] == 3
    assert client.get(file + "/versions/3/content", headers=peer).text == "original"
    assert len(client.get(file + "/versions", headers=peer).json()["versions"]) == 3
    branch = client.post(
        root + "/chat/conversations/" + conv + "/branches",
        headers=peer,
        json={"request_id": str(uuid4()), "through_sequence": 0},
    )
    assert branch.status_code == 201, branch.text
    attachments = root + "/chat/conversations/" + branch.json()["id"] + "/files"
    copied = client.get(attachments, headers=peer).json()["files"][0]
    assert copied["id"] != item["id"] and copied["version"] == 1
    copied_path = root + "/files/" + copied["id"]
    assert client.get(copied_path + "/versions/1/content", headers=peer).text == "original"
    assert (
        client.post(file + "/versions", headers=peer, json=upload("later", expected_version=3)).status_code
        == 201
    )
    assert client.get(copied_path + "/versions/1/content", headers=peer).text == "original"
    assert client.get(copied_path + "/versions", headers=owner).status_code == 404
    client.patch(
        root + "/members/" + peer_id,
        headers=owner,
        json={"version": 1, "role": "member", "active": False, "licensed": False},
    )
    assert client.get(file + "/versions/1/content", headers=peer).status_code == 404


def test_concurrent_identical_objects_are_complete_at_first_visibility(tmp_path):
    store = FileStore(FileStoreSettings(root=tmp_path))
    org, owner, data = str(uuid4()), str(uuid4()), b"A" * 1024 * 1024

    def operation(_):
        key, _ = store.put(org, owner, data)
        return store.get(key)

    with ThreadPoolExecutor(max_workers=8) as executor:
        assert all(value == data for value in executor.map(operation, range(24)))
    assert not list(tmp_path.rglob(".upload-*"))
