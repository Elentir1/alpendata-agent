import base64
from urllib.parse import urlsplit
from uuid import uuid4

import jwt
from test_chat import join
from test_office_editor import SECRET, document
from test_office_editor import service as service


def test_project_document_copy_keeps_original_private_and_revokes_editor_access(
    service, account, verification
):
    _, client = service
    _, owner = account("owner@example.com")
    peer_id, peer = account("peer@example.com")
    org = client.post("/api/organizations", headers=owner, json={"name": "Coaches"}).json()["id"]
    root = f"/api/organizations/{org}"
    join(client, verification, root, owner, peer, "peer@example.com")
    client.put(
        root + "/onboarding", headers=owner, json={"language": "fr", "role": "Coach", "needs": "Documents"}
    )
    chat = client.post(root + "/chat/conversations", headers=owner, json={}).json()["id"]
    attachments = root + "/chat/conversations/" + chat + "/files"
    original = client.post(
        attachments,
        headers=owner,
        json={
            "request_id": str(uuid4()),
            "filename": "brief.docx",
            "content_base64": base64.b64encode(document("original")).decode(),
        },
    ).json()
    project = client.post(root + "/chat/projects", headers=owner, json={"name": "Client"}).json()["id"]
    path = root + "/chat/projects/" + project
    client.put(path + "/members", headers=owner, json={"user_id": peer_id, "role": "reader"})
    assert client.get(path + "/files", headers=peer).json()["files"] == []
    publication = {"request_id": str(uuid4()), "file_id": original["id"], "version": 1}
    published = client.post(path + "/files", headers=owner, json=publication)
    assert published.status_code == 201, published.text
    copied = published.json()
    assert copied["id"] != original["id"]
    assert client.post(path + "/files", headers=owner, json=publication).json()["id"] == copied["id"]
    assert len(client.get(path + "/files", headers=peer).json()["files"]) == 1
    search = root + "/chat/search-resources?q=brief"
    hits = client.get(search, headers=peer).json()["results"]
    assert [hit["id"] for hit in hits] == [copied["id"]]
    assert hits[0]["project_id"] == project and original["id"] not in str(hits)
    assert client.get(root + "/chat?q=brief", headers=peer).json()["conversations"] == []
    assert len(client.get(attachments, headers=owner).json()["files"]) == 1
    assert client.get(root + "/files/" + original["id"] + "/versions", headers=peer).status_code == 404
    assert client.get(root + "/chat/conversations/" + chat, headers=peer).status_code == 404
    file = root + "/files/" + copied["id"]
    assert client.get(file + "/versions/1/content", headers=peer).content == document("original")
    edit = {
        "filename": "brief.docx",
        "expected_version": 1,
        "content_base64": base64.b64encode(document("contributor edit")).decode(),
    }
    assert client.post(file + "/versions", headers=peer, json=edit).status_code == 403
    assert client.post(file + "/editor", headers=peer, json={}).status_code == 403
    client.put(path + "/members", headers=owner, json={"user_id": peer_id, "role": "contributor"})
    assert client.post(file + "/versions", headers=peer, json=edit).json()["version"] == 2
    assert client.post(file + "/versions", headers=owner, json=edit).status_code == 409
    assert (
        client.post(
            file + "/compare",
            headers=peer,
            json={"before_version": 1, "after_version": 1, "other_file_id": original["id"]},
        ).status_code
        == 404
    )
    assert client.get(
        root + "/files/" + original["id"] + "/versions/1/content", headers=owner
    ).content == document("original")
    session = client.post(file + "/editor", headers=peer, json={})
    assert session.status_code == 201, session.text
    session = session.json()
    parsed = urlsplit(session["config"]["document"]["url"])
    content = parsed.path + "?" + parsed.query
    assert client.get(content).content == document("contributor edit")
    assert client.get(file + "/editor/" + session["id"], headers=peer).status_code == 200
    assert client.get(file + "/editor/" + session["id"], headers=owner).status_code == 404
    client.delete(path + "/members/" + peer_id, headers=owner)
    assert client.get(search, headers=peer).json()["results"] == []
    assert client.get(content).status_code == 404
    assert client.get(file + "/versions/1/content", headers=peer).status_code == 404
    assert client.get(file + "/editor/" + session["id"], headers=peer).status_code == 404
    signed = jwt.encode(
        {"key": session["id"], "status": 2, "url": "https://office.example.test/saved.docx"},
        SECRET,
        algorithm="HS256",
    )
    assert client.post("/api/editor/callback/" + session["id"], json={"token": signed}).status_code == 404
