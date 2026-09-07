import base64
import io
import sys
import zipfile
from uuid import uuid4

import pytest
from service_http import service_http
from test_chat import join

from alpendata_api.file_store import FileStoreSettings
from alpendata_api.model_gateway import ModelSettings
from alpendata_api.runtime import RuntimeSettings
from alpendata_api.settings import Settings

SECRET = "synthetic-office-signing-key-32-characters"


@pytest.fixture
def service(database_url, service_factory, tmp_path, monkeypatch):
    settings = Settings(
        database_url=database_url,
        files=FileStoreSettings(root=tmp_path / "objects"),
        model=ModelSettings("mistral", "synthetic-model", "synthetic-key"),
        runtime=RuntimeSettings(tmp_path / "states", "sha256:" + "0" * 64, executable=sys.executable),
        office_origin="https://office.example.test",
        office_secret=SECRET,
        smtp_host="smtp.example.test",
        smtp_sender="noreply@example.com",
        smtp_username="synthetic",
        smtp_password="synthetic",
    )
    discovery = b'<wopi-discovery><net-zone><app><action name="edit" ext="docx" urlsrc="https://office.example.test/browser/build/cool.html?"/></app></net-zone></wopi-discovery>'
    with service_http(lambda _: (200, {}, discovery)) as (transport, _):
        monkeypatch.setattr("alpendata_api.office_discovery.requests.Session", lambda: transport)
        with service_factory(settings) as pair:
            yield pair


def document(text):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as package:
        package.writestr(
            zipfile.ZipInfo("[Content_Types].xml", date_time=(2020, 1, 1, 0, 0, 0)),
            '<Types><Override PartName="/word/document.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
        )
        package.writestr(
            zipfile.ZipInfo("word/document.xml", date_time=(2020, 1, 1, 0, 0, 0)),
            "<document>" + text + "</document>",
        )
    return stream.getvalue()


def editor_urls(session):
    path = "/api/editor/wopi/files/" + session["id"]
    return path, {"access_token": session["access_token"]}


def test_wopi_saves_keep_snapshots_conflicts_and_revoke_access(service, account, verification):
    app, client = service
    _, owner = account("owner@example.com")
    peer_id, peer = account("peer@example.com")
    org = client.post("/api/organizations", headers=owner, json={"name": "PME"}).json()["id"]
    root = f"/api/organizations/{org}"
    join(client, verification, root, owner, peer, "peer@example.com")
    client.put(
        root + "/onboarding", headers=peer, json={"language": "en", "role": "Coach", "needs": "Documents"}
    )
    conv = client.post(root + "/chat/conversations", headers=peer, json={}).json()["id"]

    def encode(text):
        return base64.b64encode(document(text)).decode()

    item = client.post(
        root + "/chat/conversations/" + conv + "/files",
        headers=peer,
        json={"request_id": str(uuid4()), "filename": "brief.docx", "content_base64": encode("original")},
    ).json()
    file = root + "/files/" + item["id"]
    session = client.post(file + "/editor", headers=peer, json={"language": "en", "mobile": True}).json()
    assert "lang=en" in session["action_url"] and "access_token" not in session["action_url"]
    wopi, params = editor_urls(session)
    info = client.get(wopi, params=params).json()
    assert info["SupportsLocks"] and info["Version"].endswith(":1")
    assert client.get(wopi + "/contents", params=params).content == document("original")
    assert client.get(wopi).status_code == 401
    assert client.get(wopi.replace(session["id"], str(uuid4())), params=params).status_code == 401
    lock = {"X-WOPI-Override": "LOCK", "X-WOPI-Lock": "first-lock"}
    put = {"X-WOPI-Override": "PUT", "X-WOPI-Lock": "first-lock"}

    def save(text, headers=put):
        return client.post(wopi + "/contents", params=params, headers=headers, content=document(text))

    assert save("before lock").status_code == 409
    assert client.post(wopi, params=params, headers=lock).status_code == 200
    mismatch = client.post(wopi, params=params, headers={**lock, "X-WOPI-Lock": "other"})
    assert mismatch.status_code == 409 and mismatch.headers["X-WOPI-Lock"] == "first-lock"
    assert save("manual v2").headers["X-WOPI-ItemVersion"].endswith(":2")
    assert save("manual v2").headers["X-WOPI-ItemVersion"].endswith(":2")
    assert client.get(wopi + "/contents", params=params).content == document("manual v2")
    assert (
        client.post(
            file + "/versions",
            headers=peer,
            json={"expected_version": 2, "filename": "brief.docx", "content_base64": encode("assistant v3")},
        ).status_code
        == 201
    )
    # An acknowledged retry after an external edit neither overwrites nor creates a spurious copy.
    assert save("manual v2").status_code == 200
    assert client.get(file + "/editor/" + session["id"], headers=peer).json()["conflict_file_id"] is None
    assert client.get(wopi + "/contents", params=params).content == document("manual v2")
    assert save("manual conflict").status_code == 200
    assert save("manual conflict").status_code == 200
    conflict = client.get(file + "/editor/" + session["id"], headers=peer).json()["conflict_file_id"]
    assert conflict and conflict != item["id"]
    assert client.get(file + "/versions/3/content", headers=peer).content == document("assistant v3")
    conflict_path = root + "/files/" + conflict
    assert len(client.get(conflict_path + "/versions", headers=peer).json()["versions"]) == 1
    assert client.get(conflict_path + "/versions", headers=owner).status_code == 404
    assert client.get(wopi + "/contents", params=params).content == document("manual conflict")
    assert (
        client.post(
            conflict_path + "/versions",
            headers=peer,
            json={
                "expected_version": 1,
                "filename": "brief (copie).docx",
                "content_base64": encode("external conflict edit"),
            },
        ).status_code
        == 201
    )
    assert save("second conflict").status_code == 200
    new_copy = client.get(file + "/editor/" + session["id"], headers=peer).json()["conflict_file_id"]
    assert new_copy != conflict
    assert client.get(conflict_path + "/versions/2/content", headers=peer).content == document(
        "external conflict edit"
    )
    # Locks survive requests, expire, and can be atomically replaced.
    from alpendata_api.models import EditorSession, now

    with app.state.session_factory.begin() as db:
        db.get(EditorSession, session["id"]).lock_expires_at = now() - 1
    assert save("expired").status_code == 409
    assert client.post(wopi, params=params, headers=lock).status_code == 200
    assert (
        client.post(
            wopi, params=params, headers={**lock, "X-WOPI-OldLock": "first-lock", "X-WOPI-Lock": "new-lock"}
        ).status_code
        == 200
    )
    assert save("old lock").status_code == 409
    assert client.post(wopi, params=params, headers={"X-WOPI-Override": "RENAME_FILE"}).status_code == 501
    client.patch(
        root + "/members/" + peer_id,
        headers=owner,
        json={"version": 1, "role": "member", "active": False, "licensed": False},
    )
    assert client.get(wopi, params=params).status_code in (403, 404)
    assert client.get(wopi + "/contents", params=params).status_code in (403, 404)
    assert save("revoked", {**put, "X-WOPI-Lock": "new-lock"}).status_code in (403, 404)
