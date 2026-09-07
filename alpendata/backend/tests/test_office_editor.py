import base64
import io
import sys
import zipfile
from urllib.parse import urlsplit
from uuid import uuid4

import jwt
import pytest
from service_http import service_http
from test_chat import join

from alpendata_api.file_store import FileStoreSettings
from alpendata_api.model_gateway import ModelSettings
from alpendata_api.runtime import RuntimeSettings
from alpendata_api.settings import Settings

SECRET = "synthetic-office-signing-key-32-characters"


@pytest.fixture
def service(database_url, service_factory, tmp_path):
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


def test_signed_editor_callbacks_keep_both_versions_and_revoke_temporary_access(
    service, account, verification, monkeypatch
):
    _, client = service
    _, owner = account("owner@example.com")
    peer_id, peer = account("peer@example.com")
    org = client.post("/api/organizations", headers=owner, json={"name": "PME"}).json()["id"]
    root = f"/api/organizations/{org}"
    join(client, verification, root, owner, peer, "peer@example.com")
    client.put(
        root + "/onboarding", headers=peer, json={"language": "en", "role": "Coach", "needs": "Documents"}
    )
    conv = client.post(root + "/chat/conversations", headers=peer, json={}).json()["id"]
    path = root + "/chat/conversations/" + conv + "/files"

    def encode(text):
        return base64.b64encode(document(text)).decode()

    item = client.post(
        path,
        headers=peer,
        json={"request_id": str(uuid4()), "filename": "brief.docx", "content_base64": encode("original")},
    ).json()
    file = root + "/files/" + item["id"]
    session = client.post(file + "/editor", headers=peer, json={"language": "en", "mobile": True}).json()
    signed = jwt.decode(session["config"]["token"], SECRET, algorithms=["HS256"])
    assert signed["editorConfig"]["lang"] == "en" and signed["type"] == "mobile"
    download = urlsplit(session["config"]["document"]["url"])
    content_url = download.path + "?" + download.query
    assert client.get(content_url).content == document("original")
    # An assistant edit lands after the Office session opened.
    assert (
        client.post(
            file + "/versions",
            headers=peer,
            json={
                "expected_version": 1,
                "filename": "brief.docx",
                "content_base64": encode("assistant edit"),
            },
        ).status_code
        == 201
    )
    callback = "/api/editor/callback/" + session["id"]
    payload = {"key": session["id"], "status": 2, "url": "https://office.example.test/saved.docx"}
    assert client.post(callback, json=payload).status_code == 403
    assert client.post(callback, json={**payload, "token": session["config"]["token"]}).status_code == 403
    with service_http(lambda _: (200, {}, document("manual edit"))) as (transport, calls):
        # The provider transport is real HTTP; only its document payload is synthetic.
        monkeypatch.setattr("alpendata_api.office_editor.requests.Session", lambda: transport)
        token = jwt.encode(payload, SECRET, algorithm="HS256")
        assert client.post(callback, json={"token": token}).json() == {"error": 0}
        assert client.post(callback, json={"token": token}).json() == {"error": 0}
        assert len(calls) == 2
    status = client.get(file + "/editor/" + session["id"], headers=peer).json()
    conflict = status["conflict_file_id"]
    assert conflict and conflict != item["id"]
    assert client.get(file + "/versions/2/content", headers=peer).content == document("assistant edit")
    assert client.get(root + "/files/" + conflict + "/versions/1/content", headers=peer).content == document(
        "manual edit"
    )
    assert len(client.get(root + "/files/" + conflict + "/versions", headers=peer).json()["versions"]) == 1
    assert client.get(root + "/files/" + conflict + "/versions", headers=owner).status_code == 404
    client.patch(
        root + "/members/" + peer_id,
        headers=owner,
        json={"version": 1, "role": "member", "active": False, "licensed": False},
    )
    assert client.get(content_url).status_code in (403, 404)
    assert client.post(callback, json={"token": token}).status_code in (403, 404)
