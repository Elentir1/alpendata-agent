"""Reviewed personal writes through real API, MSAL, vault and database boundaries."""

import base64
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from requests import Timeout
from test_documents import example_pdf, start_document_turn
from test_microsoft_connections import connected_service as connected_service
from test_microsoft_connections import start
from test_sharepoint_documents import FileHTTP, response
from test_sharepoint_documents import download_service as download_service

from alpendata_api.chat_worker import ChatWorker
from alpendata_api.microsoft_data import CALLBACK
from alpendata_api.models import SharePointSave, now


class SaveHTTP(FileHTTP):
    def __init__(self):
        super().__init__(example_pdf())
        self.existing = None
        self.writes = []
        self.uploads = []
        self.outcome = 201
        self.started = self.release = None

    def request(self, method, url, **kwargs):
        if method == "GET" and url == "https://tenant.sharepoint.com/download":
            assert kwargs["headers"] == {}
            return response(200, example_pdf())
        if method == "GET" and "/items/existing" in url:
            if url.endswith("/content"):
                return response(302, headers={"Location": "https://tenant.sharepoint.com/download"})
            return response(
                200,
                json.dumps(
                    {
                        **self.existing,
                        "size": len(example_pdf()),
                        "webUrl": "https://tenant.sharepoint.com/Plan.pdf",
                    }
                ).encode(),
            )
        if url.startswith("https://tenant.sharepoint.com/upload"):
            assert "Authorization" not in kwargs["headers"]
            assert (
                kwargs["headers"]["Content-Range"] == f"bytes 0-{len(example_pdf()) - 1}/{len(example_pdf())}"
            )
            self.uploads.append((url, kwargs))
            return self.finish(kwargs)
        if method == "POST" and url.endswith("/createUploadSession"):
            assert kwargs["json"]["item"]["@microsoft.graph.conflictBehavior"] == "fail"
            assert url.endswith("/items/folder:/Plan.pdf:/createUploadSession")
            self.writes.append((method, url, kwargs))
            return response(
                200,
                json.dumps(
                    {"uploadUrl": "https://tenant.sharepoint.com/upload?secret=upload-secret"}
                ).encode(),
            )
        if method == "PUT":
            assert url.endswith("/items/existing/content")
            assert kwargs["headers"]["If-Match"] == "version-1"
            self.writes.append((method, url, kwargs))
            return self.finish(kwargs)
        if "/items/folder" in url:
            self.calls.append((method, url, kwargs))
            if url.endswith("/children"):
                return response(200, json.dumps({"value": [self.folder()]}).encode())
            if "/items/folder:/" in url:
                return response(200, json.dumps(self.existing).encode()) if self.existing else response(404)
            return response(200, json.dumps(self.folder()).encode())
        if url.endswith("/items/document"):
            return response(
                200,
                json.dumps(
                    {
                        "id": "document",
                        "file": {},
                        "parentReference": {"driveId": "shared-drive", "id": "folder"},
                    }
                ).encode(),
            )
        return super().request(method, url, **kwargs)

    def folder(self):
        return {
            "id": "folder",
            "name": "Accompagnements",
            "folder": {},
            "webUrl": "https://tenant.sharepoint.com/Accompagnements",
            "parentReference": {"driveId": "shared-drive"},
        }

    def finish(self, kwargs):
        assert kwargs["data"] == example_pdf()
        assert kwargs["allow_redirects"] is False and kwargs["timeout"] == 20
        if self.started:
            self.started.set()
            assert self.release.wait(10)
        if self.outcome == "timeout":
            raise Timeout("Synthetic lost response")
        return response(
            self.outcome,
            json.dumps(
                {
                    "id": "existing",
                    "name": "Plan.pdf",
                    "file": {},
                    "size": len(example_pdf()),
                    "webUrl": "https://tenant.sharepoint.com/Plan.pdf",
                }
            ).encode(),
        )


@pytest.fixture
def save_service(download_service):
    app, client, settings, provider, graph, org, alice, bob = download_service
    http = SaveHTTP()
    graph.session = graph.content_session = http
    path = start_document_turn(download_service)
    worker = ChatWorker(settings, app.state.session_factory, runtime=object())
    result = worker.tool(
        worker.claim(),
        [],
        {
            "kind": "document",
            "filename": "Plan.pdf",
            "content_base64": base64.b64encode(example_pdf()).decode(),
        },
    )
    assert result["status"] == 200
    payload = {
        "artifact_id": result["body"]["id"],
        "drive_id": "shared-drive",
        "item_id": "folder",
        "filename": "Plan.pdf",
    }
    return download_service, http, payload, path


def permit(service):
    _, client, _, provider, _, org, _, bob = service
    provider.http_client.scopes = {
        "openid",
        "profile",
        "offline_access",
        "Files.Read.All",
        "Files.ReadWrite.All",
    }
    flow = start(client, provider.http_client, org, bob, capabilities=("files", "files_write"))
    assert client.post(CALLBACK, data=flow, follow_redirects=False).status_code == 303


def test_personal_review_is_required_and_confirmation_is_idempotent(save_service):
    service, http, payload, _ = save_service
    app, client, _, _, _, org, alice, bob = service
    base = f"/api/organizations/{org}/sharepoint"
    assert client.post(base + "/saves", headers=bob[2], json=payload).status_code == 403
    permit(service)
    assert client.post(base + "/saves", headers=alice[2], json=payload).status_code == 404
    folders = client.post(base + "/folders/search", headers=bob[2], json={"query": "coaching"})
    assert folders.json()["folders"][0]["name"] == "Accompagnements", folders.text
    browse = client.post(
        base + "/folders/browse", headers=bob[2], json={"drive_id": "shared-drive", "item_id": "folder"}
    )
    assert browse.json()["folder"]["name"] == "Accompagnements"
    review = client.post(base + "/saves", headers=bob[2], json=payload)
    assert review.status_code == 201, review.text
    assert review.json()["status"] == "review" and not review.json()["replaces_existing"]
    assert not http.writes
    path = base + "/saves/" + review.json()["id"]
    assert client.post(path + "/confirm", headers=alice[2], json={}).status_code == 404
    assert client.post(path + "/confirm", headers=bob[2], json={"owner_id": alice[0]}).status_code == 422
    result = client.post(path + "/confirm", headers=bob[2], json={})
    assert result.json()["status"] == "completed", result.text
    assert client.post(path + "/confirm", headers=bob[2], json={}).json() == result.json()
    assert len(http.writes) == len(http.uploads) == 1
    assert http.writes[0][2]["headers"]["Authorization"] == "Bearer synthetic-access-" + bob[1]
    assert "upload-secret" not in result.text and "synthetic-access" not in result.text
    assert client.get(path, headers=alice[2]).status_code == 404
    assert (
        client.get(
            base + "/saves", headers=alice[2], params={"artifact_id": payload["artifact_id"]}
        ).status_code
        == 404
    )
    assert (
        client.get(base + "/saves", headers=bob[2], params={"artifact_id": payload["artifact_id"]}).json()[
            "saves"
        ][0]["status"]
        == "completed"
    )
    review = client.post(base + "/saves", headers=bob[2], json=payload).json()
    with app.state.session_factory.begin() as db:
        db.get(SharePointSave, review["id"]).expires_at = now() - 1
    assert (
        client.post(base + "/saves/" + review["id"] + "/confirm", headers=bob[2], json={}).status_code == 409
    )


def test_changed_files_unknown_results_and_concurrent_confirmation_do_not_overwrite_or_repeat(save_service):
    service, http, payload, _ = save_service
    _, client, _, _, _, org, _, bob = service
    permit(service)
    base = f"/api/organizations/{org}/sharepoint/saves"
    http.existing = {"id": "existing", "name": "Plan.pdf", "file": {}, "eTag": "version-1"}
    review = client.post(base, headers=bob[2], json=payload).json()
    path = base + "/" + review["id"] + "/confirm"
    assert review["replaces_existing"]
    assert client.post(path, headers=bob[2], json={}).status_code == 409
    http.existing["eTag"] = "version-2"
    assert (
        client.post(path, headers=bob[2], json={"replace_existing": True}).json()["error_code"]
        == "sharepoint_destination_changed"
    )
    assert not http.writes
    http.existing["eTag"] = "version-1"
    review = client.post(base, headers=bob[2], json=payload).json()
    path = base + "/" + review["id"] + "/confirm"
    http.started, http.release, http.outcome = Event(), Event(), "timeout"
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(client.post, path, headers=bob[2], json={"replace_existing": True})
        assert http.started.wait(10)
        second = pool.submit(client.post, path, headers=bob[2], json={"replace_existing": True})
        http.release.set()
        assert first.result(timeout=20).json()["status"] == "unknown"
        assert second.result(timeout=20).json()["status"] in ("running", "unknown")
    assert len(http.writes) == 1
    assert client.post(path, headers=bob[2], json={"replace_existing": True}).json()["status"] == "unknown"
    assert len(http.writes) == 1
    assert client.post(base, headers=bob[2], json=payload).status_code == 409
    verification = client.post(base + "/" + review["id"] + "/verify", headers=bob[2])
    assert verification.json()["status"] == "completed", verification.text
    assert verification.json()["result"]["verified_current_content"] is True
    assert len(http.writes) == 1
