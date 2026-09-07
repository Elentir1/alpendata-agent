"""Uploaded content travels through private storage, OCI parsing and searchable references."""

import base64
from dataclasses import replace
from threading import Event, Lock
from uuid import uuid4

import pytest
from test_chat import service as service

from alpendata_api.concurrent_work import WorkspaceWork
from alpendata_api.document_worker import DocumentWorker
from alpendata_api.runtime import RuntimeSettings

pytestmark = pytest.mark.linux_only


def test_upload_analysis_and_reference_search_use_the_real_worker(service, account, request):
    image = request.config.getoption("--runtime-image")
    if not image:
        pytest.skip("Requires the actual document runtime")
    app, client = service
    _, owner = account("documents@example.com")
    org = client.post("/api/organizations", headers=owner, json={"name": "Document QA"}).json()["id"]
    root = f"/api/organizations/{org}"
    client.put(
        root + "/onboarding", headers=owner, json={"language": "en", "role": "Coach", "needs": "Documents"}
    )
    conversation = client.post(root + "/chat/conversations", headers=owner, json={}).json()["id"]
    text = "Meeting preparation\nOur reference is chrysoprase.\nNext appointment is to be confirmed."
    file = client.post(
        root + "/chat/conversations/" + conversation + "/files",
        headers=owner,
        json={
            "request_id": str(uuid4()),
            "filename": "meeting.txt",
            "content_base64": base64.b64encode(text.encode()).decode(),
        },
    ).json()
    settings = app.state.chat_settings
    worker = DocumentWorker(
        replace(settings, runtime=RuntimeSettings(settings.runtime.state_root, image)),
        app.state.session_factory,
    )
    started, release, parsed, mutex = Event(), Event(), Event(), Lock()
    occupied = [0]

    def busy_chat():
        with mutex:
            occupied[0] += 1
            if occupied[0] == 3:
                started.set()
        assert release.wait(45)

    def parse_document():
        assert started.wait(10)
        assert worker.run_once()
        parsed.set()

    work = WorkspaceWork(busy_chat, parse_document)
    try:
        for _ in range(3):
            work.tick()
        assert started.wait(10)
        assert parsed.wait(30), "Document parsing must progress while all chat slots are occupied"
    finally:
        release.set()
        work.close()
    passages = client.get(root + "/files/" + file["id"] + "/versions/1/passages", headers=owner).json()
    assert passages["status"] == "ready", passages
    assert passages["passages"][0]["reference"].startswith("lines 1")
    assert "chrysoprase" in passages["passages"][0]["text"]
    hits = client.get(root + "/chat?q=chrysoprase", headers=owner).json()["conversations"]
    assert hits[0]["id"] == conversation and "chrysoprase" in hits[0]["match"]["text"]
    assert not worker.run_once()
    updated = text.replace("chrysoprase", "amethyst")
    version = client.post(
        root + "/files/" + file["id"] + "/versions",
        headers=owner,
        json={
            "filename": "meeting.txt",
            "expected_version": 1,
            "content_base64": base64.b64encode(updated.encode()).decode(),
        },
    )
    assert version.status_code == 201, version.text
    assert worker.run_once()
    compared = client.post(
        root + "/files/" + file["id"] + "/compare",
        headers=owner,
        json={"before_version": 1, "after_version": 2},
    ).json()
    assert compared["changed_sections"] == 1 and not compared["identical_bytes"]
    assert "chrysoprase" in compared["differences"][0]["before"]
    assert "amethyst" in compared["differences"][0]["after"]
