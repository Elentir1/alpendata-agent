"""Personal Microsoft downloads retain server credentials and source provenance."""

import base64
import json
import sys
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from requests import Response
from test_documents import example_pdf, start_document_turn
from test_microsoft_connections import GraphHTTP, start
from test_microsoft_connections import connected_service as connected_service

from alpendata_api.app import create_app
from alpendata_api.chat_worker import ChatWorker
from alpendata_api.connections import MicrosoftReader
from alpendata_api.graph import GraphReader
from alpendata_api.microsoft_data import CALLBACK, MicrosoftData
from alpendata_api.model_gateway import ModelSettings
from alpendata_api.models import Conversation
from alpendata_api.runtime import RuntimeSettings


def response(status, body=b"", headers=None):
    result = Response()
    result.status_code, result._content, result._content_consumed = status, body, True
    result.headers.update(headers or {})
    return result


class FileHTTP(GraphHTTP):
    def __init__(self, content):
        super().__init__()
        self.content = content
        self.location = "https://tenant.sharepoint.com/download?signature=synthetic-private-link"
        self.changed = False

    def request(self, method, url, **kwargs):
        if "/drives/shared-drive/items/document" not in url:
            return super().request(method, url, **kwargs)
        assert method == "GET" and url.startswith("https://graph.microsoft.com/v1.0/")
        assert kwargs["allow_redirects"] is False
        self.calls.append((method, url, kwargs))
        if self.status != 200:
            return response(self.status)
        if url.endswith("/content"):
            return response(302, headers={"Location": self.location})
        metadata = {
            "id": "document",
            "name": "Plan.pdf",
            "size": len(self.content),
            "file": {},
            "eTag": "version-1",
            "webUrl": "https://tenant.sharepoint.com/Plan.pdf",
        }
        if self.changed and kwargs.get("params", {}).get("$select") == "id,eTag":
            metadata["eTag"] = "version-2"
        return response(200, json.dumps(metadata).encode())


class ContentHTTP:
    def __init__(self, content):
        self.content, self.calls, self.status = content, [], 200

    def request(self, method, url, **kwargs):
        assert method == "GET" and kwargs["headers"] == {}
        assert kwargs["allow_redirects"] is False
        self.calls.append((url, kwargs))
        return response(self.status, self.content, {"Location": "https://outside.example/never-follow"})


@pytest.fixture
def download_service(connected_service, tmp_path):
    _, original, settings, microsoft, _, org, alice, bob = connected_service
    for person in (alice, bob):
        flow = start(original, microsoft, org, person)
        assert original.post(CALLBACK, data=flow, follow_redirects=False).status_code == 303
    settings = replace(
        settings,
        model=ModelSettings("mistral", "synthetic-model", "synthetic-key"),
        runtime=RuntimeSettings(tmp_path / "states", "sha256:" + "0" * 64, executable=sys.executable),
    )
    provider = MicrosoftData(settings, http_client=microsoft)
    data = example_pdf()
    graph = GraphReader(FileHTTP(data), content_session=ContentHTTP(data))
    app = create_app(settings, microsoft_provider=provider, graph=graph)
    with TestClient(app, base_url=settings.public_origin) as client:
        yield app, client, settings, provider, graph, org, alice, bob


def test_download_uses_own_connection_and_rejects_expired_or_changed_sources(download_service):
    app, client, settings, provider, graph, org, alice, bob = download_service
    path = start_document_turn(download_service)
    worker = ChatWorker(
        settings,
        app.state.session_factory,
        runtime=object(),
        microsoft=MicrosoftReader(settings, app.state.session_factory, provider, graph),
    )
    job = worker.claim()
    payload = {
        "capability": "files",
        "operation": "download",
        "arguments": {"drive_id": "shared-drive", "item_id": "document"},
    }
    result = worker.tool(job, ["files"], payload)
    assert result["status"] == 200, result
    assert base64.b64decode(result["body"]["content_base64"]) == example_pdf()
    assert all(
        call[2]["headers"]["Authorization"] == "Bearer synthetic-access-" + bob[1]
        for call in graph.session.calls
    )
    assert graph.content_session.calls[0][1]["headers"] == {}
    assert "synthetic-private-link" not in json.dumps(result)
    assert "synthetic-access-" not in json.dumps(result)
    detail = client.get(path, headers=bob[2]).json()
    assert detail["turns"][0]["sources"] == [
        {
            "kind": "files",
            "label": "Plan.pdf",
            "url": "https://tenant.sharepoint.com/Plan.pdf",
        }
    ]
    assert "content_base64" not in json.dumps(detail)
    assert client.get(path, headers=alice[2]).status_code == 404
    before = len(graph.session.calls)
    assert worker.tool(job, [], payload)["status"] == 403
    assert worker.tool(job, ["files"], {**payload, "owner_id": alice[0]})["status"] == 400
    assert len(graph.session.calls) == before
    with app.state.session_factory.begin() as db:
        db.get(Conversation, path.rsplit("/", 1)[1]).tool_revision = 1
    assert worker.tool(job, ["files"], payload)["status"] == 403
    with app.state.session_factory.begin() as db:
        db.get(Conversation, path.rsplit("/", 1)[1]).tool_revision = 2
    graph.session.changed = True
    assert worker.tool(job, ["files"], payload)["body"]["error"] == "microsoft_file_changed"
    graph.session.changed = False
    before = len(graph.content_session.calls)
    graph.session.content = b"x" * (5 * 1024 * 1024 + 1)
    assert worker.tool(job, ["files"], payload)["status"] == 413
    assert len(graph.content_session.calls) == before
    graph.session.content = example_pdf()
    graph.content_session.content = b"x" * (5 * 1024 * 1024 + 1)
    assert worker.tool(job, ["files"], payload)["status"] == 413
    graph.content_session.content = example_pdf() + b"changed"
    assert worker.tool(job, ["files"], payload)["body"]["error"] == "microsoft_file_changed"
    graph.content_session.content = example_pdf()
    graph.content_session.status = 403
    assert worker.tool(job, ["files"], payload)["body"]["error"] == "microsoft_file_download_failed"
    assert client.get(f"/api/organizations/{org}/microsoft", headers=bob[2]).json()["status"] == "connected"
    assert client.delete(f"/api/organizations/{org}/microsoft", headers=bob[2]).status_code == 204
    before = len(graph.session.calls)
    assert worker.tool(job, ["files"], payload)["status"] == 409
    assert len(graph.session.calls) == before


def test_download_rejects_untrusted_destinations_without_following_them(download_service):
    app, _, settings, provider, graph, _, _, _ = download_service
    start_document_turn(download_service)
    worker = ChatWorker(
        settings,
        app.state.session_factory,
        runtime=object(),
        microsoft=MicrosoftReader(settings, app.state.session_factory, provider, graph),
    )
    job = worker.claim()
    payload = {
        "capability": "files",
        "operation": "download",
        "arguments": {"drive_id": "shared-drive", "item_id": "document"},
    }
    for destination in (
        "https://tenant.sharepoint.com.evil.example/file",
        "http://tenant.sharepoint.com/file",
        "https://127.0.0.1/file",
        "https://user@tenant.sharepoint.com/file",
        "https://tenant.sharepoint.com:444/file",
        "https://tenant.sharepoint.com/file#fragment",
    ):
        graph.session.location = destination
        result = worker.tool(job, ["files"], payload)
        assert result["body"]["error"] == "microsoft_download_destination_invalid", result
    assert graph.content_session.calls == []
    assert (
        worker.tool(
            job, ["files"], {**payload, "arguments": {"drive_id": "../users/other", "item_id": "document"}}
        )["status"]
        == 400
    )
