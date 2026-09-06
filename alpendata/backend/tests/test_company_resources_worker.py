import base64
import json
import shlex
import tempfile
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from model_http import completion, model_http
from test_company_resources import publication
from test_documents import example_pdf, start_document_turn
from test_routines import connected_service as connected_service
from test_routines import routine_service as routine_service

from alpendata_api.chat_worker import ChatWorker
from alpendata_api.model_gateway import ModelGateway
from alpendata_api.runtime import RuntimeSettings

pytestmark = pytest.mark.linux_only


def test_real_hermes_reads_only_granted_company_copies_and_observes_revocation(routine_service, request):
    image = request.config.getoption("--runtime-image")
    if not image:
        pytest.skip("Requires real OCI image")
    app, client, settings, _, _, org, admin, owner = routine_service
    base = f"/api/organizations/{org}/company-resources"
    note = client.post(base, headers=admin[2], json=publication(member_ids=[owner[0]])).json()
    file = client.post(
        base,
        headers=admin[2],
        json=publication(
            title="Workshop document",
            kind="document",
            text="",
            member_ids=[owner[0]],
            document={"filename": "Workshop.pdf", "content_base64": base64.b64encode(example_pdf()).decode()},
        ),
    ).json()
    client.post(
        base,
        headers=admin[2],
        json=publication(title="Hidden administrative note", text="PRIVATE-ADMIN-ONLY"),
    )
    path = start_document_turn(routine_service)
    prefixes = []
    revoked = False

    def respond(body):
        assert "PRIVATE-ADMIN-ONLY" not in json.dumps(body)
        assert "Hidden administrative note" not in json.dumps(body)
        assert "alpendata_company_resources" in {tool["function"]["name"] for tool in body.get("tools", [])}
        prefixes.append(body["messages"][0])
        start = max(i for i, message in enumerate(body["messages"]) if message["role"] == "user")
        answers = [m for m in body["messages"][start:] if m["role"] == "tool"]
        if revoked:
            if answers:
                assert json.loads(answers[-1]["content"])["status"] == 404
                return 200, completion(body, content="The resource is no longer shared with you."), {}
            name, arguments = (
                "alpendata_company_resources",
                {"action": "read", "resource_id": note["id"], "version": note["version"]},
            )
        else:
            local = json.loads(answers[2]["content"])["path"] if len(answers) > 2 else None
            if len(answers) == 4:
                assert "Coaching session" in json.loads(answers[-1]["content"])["output"]
                assert publication()["text"] in answers[1]["content"]
                return (
                    200,
                    completion(body, content="Company guidelines and the workshop document were reviewed."),
                    {},
                )
            program = (
                "from pypdf import PdfReader; print(PdfReader(" + repr(local) + ").pages[0].extract_text())"
            )
            calls = [
                ("alpendata_company_resources", {"action": "search"}),
                (
                    "alpendata_company_resources",
                    {"action": "read", "resource_id": note["id"], "version": note["version"]},
                ),
                (
                    "alpendata_company_resources",
                    {"action": "download", "resource_id": file["id"], "version": file["version"]},
                ),
                ("terminal", {"command": "/opt/venv/bin/python -c " + shlex.quote(program)}),
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
        tempfile.TemporaryDirectory(prefix="alpendata-company-") as state,
        model_http(respond) as (transport, _, _),
    ):
        settings = replace(settings, runtime=RuntimeSettings(Path(state), image))
        worker = ChatWorker(
            settings,
            app.state.session_factory,
            gateway=ModelGateway(settings.model, session=transport),
            microsoft=object(),
        )
        assert worker.run_once()
        turn = client.get(path, headers=owner[2]).json()["turns"][0]
        assert turn["status"] == "completed", turn
        assert {s["label"] for s in turn["sources"]} == {note["title"] + " · v1", file["title"] + " · v1"}
        assert (
            client.patch(
                base + "/" + note["id"] + "/access",
                headers=admin[2],
                json={"version": 1, "audience": "selected", "member_ids": [], "confirmed": True},
            ).status_code
            == 200
        )
        revoked = True
        assert (
            client.post(
                path + "/turns",
                headers=owner[2],
                json={"request_id": str(uuid4()), "message": "Read the company note again"},
            ).status_code
            == 202
        )
        assert worker.run_once()
        turns = client.get(path, headers=owner[2]).json()["turns"]
        assert turns[-1]["status"] == "completed" and "no longer shared" in turns[-1]["response"]
        assert prefixes[-1] == prefixes[0]
