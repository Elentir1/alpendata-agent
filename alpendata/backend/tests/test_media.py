import base64
import io
import json
import sys
import wave
from uuid import uuid4

import pytest
from service_http import service_http
from test_chat import join

from alpendata_api.chat_worker import ChatWorker
from alpendata_api.file_store import FileStoreSettings
from alpendata_api.model_gateway import ModelSettings
from alpendata_api.runtime import RuntimeSettings
from alpendata_api.settings import Settings


@pytest.fixture
def service(database_url, service_factory, tmp_path):
    settings = Settings(
        database_url=database_url,
        files=FileStoreSettings(root=tmp_path / "objects"),
        model=ModelSettings("mistral", "synthetic-main", "synthetic-model-key"),
        runtime=RuntimeSettings(tmp_path / "states", "sha256:" + "0" * 64, executable=sys.executable),
        vision_model="synthetic-vision",
        transcription_model="synthetic-transcription",
        smtp_host="smtp.example.test",
        smtp_sender="noreply@example.com",
        smtp_username="synthetic",
        smtp_password="synthetic",
    )
    with service_factory(settings) as pair:
        pair[0].state.media_settings = settings
        yield pair


def test_dictation_is_private_idempotent_and_never_sends_a_chat_message(
    service, account, verification, monkeypatch
):
    app, client = service
    _, owner = account("owner@example.com")
    _, peer = account("peer@example.com")
    org = client.post("/api/organizations", headers=owner, json={"name": "Coaches"}).json()["id"]
    root = f"/api/organizations/{org}"
    join(client, verification, root, owner, peer, "peer@example.com")
    client.put(
        root + "/onboarding", headers=owner, json={"language": "fr", "role": "Coach", "needs": "Documents"}
    )
    conversation = client.post(root + "/chat/conversations", headers=owner, json={}).json()["id"]
    path = root + "/chat/conversations/" + conversation
    audio = io.BytesIO()
    with wave.open(audio, "wb") as recording:
        recording.setnchannels(1)
        recording.setsampwidth(2)
        recording.setframerate(16000)
        recording.writeframes(b"\x00\x00" * 100)
    body = {
        "request_id": str(uuid4()),
        "language": "fr",
        "media_type": "audio/wav",
        "content_base64": base64.b64encode(audio.getvalue()).decode(),
    }
    with service_http(
        lambda request: (
            200,
            {},
            json.dumps({"text": "Prépare mon rendez-vous.", "model": "synthetic-transcription"}).encode(),
        )
    ) as (transport, calls):
        monkeypatch.setattr("alpendata_api.media_provider.requests.Session", lambda: transport)
        result = client.post(path + "/dictations", headers=owner, json=body)
        assert result.status_code == 200 and result.json()["status"] == "completed", result.text
        assert client.post(path + "/dictations", headers=owner, json=body).json() == result.json()
        assert len(calls) == 1 and calls[0]["path"] == "/v1/audio/transcriptions"
        assert calls[0]["headers"]["Authorization"] == "Bearer synthetic-model-key"
        assert b"synthetic-transcription" in calls[0]["body"]
        assert client.get(path, headers=owner).json()["turns"] == []
        assert client.get(path + "/dictations/" + body["request_id"], headers=peer).status_code == 404
        assert client.post(path + "/dictations", headers=peer, json=body).status_code == 404
        assert (
            client.post(path + "/dictations", headers=owner, json={**body, "language": "en"}).status_code
            == 409
        )


def test_vision_only_reads_the_current_conversation_and_identifies_the_specialist(
    service, account, monkeypatch
):
    app, client = service
    settings = app.state.media_settings
    _, owner = account("owner@example.com")
    org = client.post("/api/organizations", headers=owner, json={"name": "Coaches"}).json()["id"]
    root = f"/api/organizations/{org}"
    client.put(
        root + "/onboarding", headers=owner, json={"language": "en", "role": "Coach", "needs": "Images"}
    )
    paths = [
        root
        + "/chat/conversations/"
        + client.post(root + "/chat/conversations", headers=owner, json={}).json()["id"]
        for _ in range(2)
    ]
    image = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a9V8AAAAASUVORK5CYII="
    file = client.post(
        paths[0] + "/files",
        headers=owner,
        json={"request_id": str(uuid4()), "filename": "image.png", "content_base64": image},
    ).json()
    client.post(
        paths[1] + "/turns", headers=owner, json={"request_id": str(uuid4()), "message": "Read my image"}
    )
    worker = ChatWorker(settings, app.state.session_factory, runtime=object())
    job = worker.claim()
    payload = {"kind": "vision", "file_id": file["id"], "version": 1, "question": "Describe this image"}
    response = {
        "model": "synthetic-vision-dated",
        "choices": [{"message": {"content": "A small light image."}}],
    }
    with service_http(lambda _: (200, {}, json.dumps(response).encode())) as (transport, calls):
        monkeypatch.setattr("alpendata_api.media_provider.requests.Session", lambda: transport)
        assert worker.tool(job, [], payload)["status"] == 404
        assert not calls
        file = client.post(
            paths[1] + "/files",
            headers=owner,
            json={"request_id": str(uuid4()), "filename": "image.png", "content_base64": image},
        ).json()
        payload["file_id"] = file["id"]
        result = worker.tool(job, [], payload)
        assert result["status"] == 200 and result["body"]["model"] == "synthetic-vision-dated", result
        assert worker.tool(job, [], payload) == result
        assert len(calls) == 1
        request = json.loads(calls[0]["body"])
        assert request["model"] == "synthetic-vision" and "tools" not in request
        assert request["messages"][1]["content"][1]["image_url"].startswith("data:image/png;base64,")
        assert client.get(paths[1], headers=owner).json()["turns"][0]["specialist_models"] == [
            "synthetic-vision-dated"
        ]
