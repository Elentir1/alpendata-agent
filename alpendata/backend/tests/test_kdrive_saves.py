"""Personal DAV writes keep review, version and idempotence boundaries."""

import base64
from uuid import uuid4

from service_http import service_http
from test_documents import example_pdf, start_document_turn
from test_infomaniak_dav import multistatus
from test_microsoft_connections import connected_service as connected_service
from test_routines import routine_service as routine_service

from alpendata_api.chat_worker import ChatWorker


def test_kdrive_review_private_credentials_versions_and_uncertain_writes(routine_service, monkeypatch):
    app, client, settings, _, _, org, alice, bob = routine_service
    start_document_turn(routine_service)
    worker = ChatWorker(settings, app.state.session_factory, runtime=object())
    artifact = worker.tool(
        worker.claim(),
        [],
        {
            "kind": "document",
            "filename": "Plan.pdf",
            "content_base64": base64.b64encode(example_pdf()).decode(),
        },
    )["body"]
    state = {"existing": False, "outcome": 201}
    folder = multistatus(
        "<d:response><d:href>/</d:href><d:propstat><d:prop>"
        "<d:resourcetype><d:collection/></d:resourcetype></d:prop>"
        "<d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>"
    )
    file = multistatus(
        "<d:response><d:href>/Plan.pdf</d:href><d:propstat><d:prop>"
        '<d:getetag>"version-1"</d:getetag></d:prop>'
        "<d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>"
    )

    def respond(request):
        if request["method"] == "PUT":
            assert request["path"] == "/Plan.pdf" and request["body"] == example_pdf()
            return state["outcome"], {"ETag": '"version-2"'}, b""
        if request["path"] == "/Plan.pdf":
            return (207, {}, file) if state["existing"] else (404, {}, b"")
        return 207, {}, folder

    with service_http(respond) as (transport, calls):
        monkeypatch.setattr("alpendata_api.infomaniak_dav.requests.Session", lambda: transport)
        connected = client.put(
            f"/api/organizations/{org}/integrations/infomaniak/dav",
            headers=bob[2],
            json={
                "service": "files",
                "username": "synthetic-user",
                "password": "synthetic-password",
                "drive_id": "12345",
                "allow_write": True,
            },
        )
        assert connected.status_code == 200, connected.text
        base = f"/api/organizations/{org}/kdrive"
        payload = {"request_id": str(uuid4()), "artifact_id": artifact["id"]}
        assert client.post(base + "/saves", headers=alice[2], json=payload).status_code == 404
        review = client.post(base + "/saves", headers=bob[2], json=payload)
        assert review.status_code == 201, review.text
        assert review.json()["status"] == "review"
        assert not [call for call in calls if call["method"] == "PUT"]
        assert client.post(base + "/saves", headers=bob[2], json=payload).json() == review.json()
        path = base + "/saves/" + review.json()["id"]
        assert client.post(path + "/confirm", headers=alice[2], json={}).status_code == 404
        assert (
            client.post(
                path.replace("/kdrive/", "/sharepoint/") + "/confirm", headers=bob[2], json={}
            ).status_code
            == 404
        )
        result = client.post(path + "/confirm", headers=bob[2], json={})
        assert result.json()["status"] == "completed", result.text
        assert client.post(path + "/confirm", headers=bob[2], json={}).json() == result.json()
        writes = [call for call in calls if call["method"] == "PUT"]
        assert len(writes) == 1 and writes[0]["headers"]["If-None-Match"] == "*"
        assert (
            writes[0]["headers"]["Authorization"]
            == "Basic " + base64.b64encode(b"synthetic-user:synthetic-password").decode()
        )

        state.update(existing=True, outcome=412)
        payload["request_id"] = str(uuid4())
        review = client.post(base + "/saves", headers=bob[2], json=payload).json()
        path = base + "/saves/" + review["id"]
        assert review["replaces_existing"]
        assert client.post(path + "/confirm", headers=bob[2], json={}).status_code == 409
        result = client.post(path + "/confirm", headers=bob[2], json={"replace_existing": True})
        assert result.json()["error_code"] == "document_version_changed", result.text
        assert result.json()["status"] == "failed"
        state["outcome"] = 503
        payload["request_id"] = str(uuid4())
        review = client.post(base + "/saves", headers=bob[2], json=payload).json()
        path = base + "/saves/" + review["id"]
        result = client.post(path + "/confirm", headers=bob[2], json={"replace_existing": True})
        assert result.json()["status"] == "unknown", result.text
        assert (
            client.post(path + "/confirm", headers=bob[2], json={"replace_existing": True}).json()
            == result.json()
        )
        writes = [call for call in calls if call["method"] == "PUT"]
        assert len(writes) == 3 and writes[-1]["headers"]["If-Match"] == '"version-1"'
        payload["request_id"] = str(uuid4())
        review = client.post(base + "/saves", headers=bob[2], json=payload).json()
        assert (
            client.post(
                base + "/saves/" + review["id"] + "/confirm", headers=bob[2], json={"replace_existing": True}
            ).status_code
            == 409
        )
        assert len([call for call in calls if call["method"] == "PUT"]) == 3
