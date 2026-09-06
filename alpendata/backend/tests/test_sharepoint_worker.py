"""Hermes searches, downloads, reads and publishes a personally authorized file."""

import json
import shlex
import tempfile
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from model_http import completion, model_http
from test_documents import example_pdf, start_document_turn
from test_microsoft_connections import connected_service as connected_service
from test_sharepoint_documents import download_service as download_service

from alpendata_api.chat_worker import ChatWorker
from alpendata_api.connections import MicrosoftReader
from alpendata_api.model_gateway import ModelGateway
from alpendata_api.runtime import RuntimeSettings

pytestmark = pytest.mark.linux_only


def test_hermes_reads_downloaded_sharepoint_content_without_credentials(download_service, request):
    image = request.config.getoption("--runtime-image")
    if not image or not request.config.getoption("--postgresql-bin"):
        pytest.skip("Requires real OCI image and PostgreSQL")
    app, client, settings, provider, graph, org, alice, bob = download_service
    path = start_document_turn(download_service)

    def respond(body):
        names = {tool["function"]["name"] for tool in body.get("tools", [])}
        assert "alpendata_download_file" in names
        assert "synthetic-private-link" not in json.dumps(body)
        assert "synthetic-access-" not in json.dumps(body)
        answers = [item for item in body["messages"] if item["role"] == "tool"]
        local = None
        if len(answers) > 1:
            downloaded = json.loads(answers[1]["content"])
            assert downloaded["status"] == 200, downloaded
            assert "content_base64" not in downloaded
            local = downloaded["path"]
            assert local.startswith("sources/") and local.endswith(".pdf")
        if len(answers) > 2:
            read = json.loads(answers[2]["content"])
            assert read["exit_code"] == 0, read
            assert "Coaching session" in read["output"]
        if len(answers) == 4:
            assert json.loads(answers[3]["content"])["status"] == 200
            return 200, completion(body, content="The document contains a coaching session heading."), {}
        program = "from pypdf import PdfReader; print(PdfReader(" + repr(local) + ").pages[0].extract_text())"
        calls = [
            ("alpendata_files", {"query": "coaching"}),
            ("alpendata_download_file", {"drive_id": "shared-drive", "item_id": "document"}),
            ("terminal", {"command": "/opt/venv/bin/python -c " + shlex.quote(program)}),
            ("alpendata_publish_document", {"path": local}),
        ]
        name, arguments = calls[len(answers)]
        result = completion(body, content=None)
        result["choices"][0]["finish_reason"] = "tool_calls"
        result["choices"][0]["message"]["tool_calls"] = [
            {
                "id": uuid4().hex[:9],
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments)},
            }
        ]
        return 200, result, {}

    with (
        tempfile.TemporaryDirectory(prefix="alpendata-sharepoint-") as state,
        model_http(respond) as (transport, _, _),
    ):
        settings = replace(settings, runtime=RuntimeSettings(Path(state), image))
        worker = ChatWorker(
            settings,
            app.state.session_factory,
            gateway=ModelGateway(settings.model, session=transport),
            microsoft=MicrosoftReader(settings, app.state.session_factory, provider, graph),
        )
        assert worker.run_once()
        turn = client.get(path, headers=bob[2]).json()["turns"][0]
        assert turn["status"] == "completed", turn
        assert any(source["label"] == "Plan.pdf" for source in turn["sources"])
        assert len(turn["artifacts"]) == 1
        assert turn["artifacts"][0]["filename"] == "Plan.pdf"
        url = f"/api/organizations/{org}/documents/{turn['artifacts'][0]['id']}/download"
        assert client.get(url, headers=bob[2]).content == example_pdf()
        assert client.get(url, headers=alice[2]).status_code == 404
