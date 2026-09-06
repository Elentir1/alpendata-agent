import sys
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from alpendata_api.chat_worker import ChatWorker
from alpendata_api.model_gateway import ModelSettings
from alpendata_api.models import ChatTurn, Conversation, ModelCall, now
from alpendata_api.runtime import RuntimeSettings
from alpendata_api.settings import Settings


@pytest.fixture
def service(database_url, service_factory, tmp_path):
    settings = Settings(
        database_url=database_url,
        smtp_sender="noreply@example.com",
        smtp_host="smtp.example.test",
        smtp_username="synthetic",
        smtp_password="synthetic",
        model=ModelSettings("mistral", "synthetic-model", "synthetic-key"),
        runtime=RuntimeSettings(tmp_path / "states", "sha256:" + "0" * 64, executable=sys.executable),
    )
    with service_factory(settings) as (app, client):
        app.state.chat_settings = settings
        yield app, client


def join(client, verification, base, admin, colleague, email):
    token = client.post(base + "/invitations", headers=admin, json={"email": email}).json()["token"]
    proof = verification(colleague, token)
    assert (
        client.post(
            "/api/invitations/accept", headers=colleague, json={"token": token, "verification_token": proof}
        ).status_code
        == 200
    )


def test_private_chat_idempotency_cancel_and_frozen_profile(service, account, verification):
    app, client = service
    _, admin = account("admin@example.com")
    colleague_id, colleague = account("colleague@example.com")
    _, outsider = account("outsider@example.com")
    org = client.post("/api/organizations", headers=admin, json={"name": "Coaches"}).json()["id"]
    base = f"/api/organizations/{org}"
    join(client, verification, base, admin, colleague, "colleague@example.com")
    client.put(
        base + "/onboarding",
        headers=colleague,
        json={"language": "fr", "role": "Coach", "needs": "Prepare client meetings"},
    )
    path = base + "/chat"
    conversation = client.post(path + "/conversations", headers=colleague, json={"language": "fr"})
    assert conversation.status_code == 201
    identifier = conversation.json()["id"]
    personal = path + "/conversations/" + identifier
    assert client.get(path, headers=admin).json()["conversations"] == []
    assert client.get(personal, headers=admin).status_code == 404
    assert client.get(personal, headers=outsider).status_code == 404
    assert (
        client.post(path + "/conversations", headers=admin, json={"owner_id": colleague_id}).status_code
        == 422
    )
    payload = {"request_id": str(uuid4()), "message": "Prepare a private briefing"}
    first = client.post(personal + "/turns", headers=colleague, json=payload)
    assert first.status_code == 202 and first.json()["status"] == "queued"
    assert client.post(personal + "/turns", headers=colleague, json=payload).json() == first.json()
    assert (
        client.post(
            personal + "/turns", headers=colleague, json={**payload, "message": "A different task"}
        ).status_code
        == 409
    )
    assert (
        client.post(
            personal + "/turns", headers=colleague, json={**payload, "request_id": str(uuid4())}
        ).status_code
        == 409
    )
    cancel = personal + "/turns/" + first.json()["id"] + "/cancel"
    assert client.post(cancel, headers=admin).status_code == 404
    assert client.post(cancel, headers=colleague).json()["status"] == "cancelled"
    assert client.post(cancel, headers=colleague).json()["status"] == "cancelled"
    read = client.get(personal, headers=colleague)
    assert read.json()["turns"][0]["message"] == payload["message"]
    assert read.headers["Cache-Control"] == "no-store"
    assert not {"system_prompt", "capabilities", "lease_id"} & read.json().keys()
    with app.state.session_factory() as db:
        saved = db.get(Conversation, identifier)
        prompt = saved.system_prompt
        assert "Prepare client meetings" in prompt
        assert saved.capabilities == []
    client.put(base + "/onboarding", headers=colleague, json={"language": "en", "needs": "Changed profile"})
    with app.state.session_factory() as db:
        assert db.get(Conversation, identifier).system_prompt == prompt
    second = client.post(
        personal + "/turns", headers=colleague, json={"request_id": str(uuid4()), "message": "Continue"}
    ).json()
    assert second["sequence"] == 2
    changes = {"version": 1, "role": "member", "active": True, "licensed": False}
    assert client.patch(base + "/members/" + colleague_id, headers=admin, json=changes).status_code == 200
    assert client.get(personal, headers=colleague).status_code == 200
    assert (
        client.post(
            personal + "/turns", headers=colleague, json={"request_id": str(uuid4()), "message": "No license"}
        ).status_code
        == 403
    )
    assert (
        client.post(personal + "/turns/" + second["id"] + "/cancel", headers=colleague).json()["status"]
        == "cancelled"
    )
    changes["active"] = False
    changes["version"] = 2
    client.patch(base + "/members/" + colleague_id, headers=admin, json=changes)
    assert client.get(personal, headers=colleague).status_code == 404


def test_queue_recovery_preserves_unknown_usage_and_database_owner_keys(service, account, verification):
    app, client = service
    _, admin = account("admin@example.com")
    peer_id, peer = account("peer@example.com")
    org = client.post("/api/organizations", headers=admin, json={"name": "Coaches"}).json()["id"]
    base = f"/api/organizations/{org}"
    join(client, verification, base, admin, peer, "peer@example.com")
    assert (
        client.post(base + "/chat/conversations", headers=admin, json={}).json()["detail"]
        == "onboarding_required"
    )
    client.put(
        base + "/onboarding", headers=admin, json={"language": "fr", "role": "Coach", "needs": "Briefing"}
    )
    identifier = client.post(base + "/chat/conversations", headers=admin, json={}).json()["id"]
    personal = base + "/chat/conversations/" + identifier
    queued = client.post(
        personal + "/turns", headers=admin, json={"request_id": str(uuid4()), "message": "Prepare briefing"}
    ).json()
    # This scenario exercises the database queue only. No runtime operation is invoked.
    worker = ChatWorker(app.state.chat_settings, app.state.session_factory, runtime=object())
    job = worker.claim()
    assert job.id == queued["id"] and worker.claim() is None
    with app.state.session_factory.begin() as db:
        turn = db.get(ChatTurn, job.id)
        turn.lease_expires_at = now() - 1
        db.add(
            ModelCall(
                turn_id=turn.id,
                organization_id=org,
                owner_id=turn.owner_id,
                provider="mistral",
                model="synthetic-model",
            )
        )
    worker.recover_expired()
    assert worker.claim() is None
    result = client.get(personal, headers=admin).json()["turns"][0]
    assert result["status"] == "interrupted" and result["response"] is None
    with app.state.session_factory() as db:
        call = db.scalar(select(ModelCall).where(ModelCall.turn_id == job.id))
        assert call.total_tokens is None and call.error_code == "model_result_unknown"
    with pytest.raises(IntegrityError), app.state.session_factory.begin() as db:
        db.add(
            ChatTurn(
                conversation_id=identifier,
                organization_id=org,
                owner_id=peer_id,
                request_id=str(uuid4()),
                sequence=2,
                message="Cross-owner insertion",
            )
        )
        db.flush()
    with pytest.raises(IntegrityError), app.state.session_factory.begin() as db:
        db.add(
            ModelCall(
                turn_id=job.id,
                organization_id=org,
                owner_id=peer_id,
                provider="mistral",
                model="synthetic-model",
            )
        )
        db.flush()


@pytest.mark.linux_only
def test_concurrent_chat_submission_and_claim_have_one_execution(service, account, request):
    if not request.config.getoption("--postgresql-bin"):
        pytest.skip("Requires PostgreSQL row locks")
    app, client = service
    _, admin = account("admin@example.com")
    org = client.post("/api/organizations", headers=admin, json={"name": "Coaches"}).json()["id"]
    client.put(
        f"/api/organizations/{org}/onboarding",
        headers=admin,
        json={"language": "fr", "role": "Coach", "needs": "Briefing"},
    )
    path = f"/api/organizations/{org}/chat/conversations"
    identifier = client.post(path, headers=admin, json={}).json()["id"]
    payload = {"request_id": str(uuid4()), "message": "One execution only"}
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(client.post, path + "/" + identifier + "/turns", headers=admin, json=payload)
            for _ in range(2)
        ]
        results = [future.result(timeout=15) for future in futures]
    assert all(result.status_code == 202 for result in results)
    assert results[0].json()["id"] == results[1].json()["id"]
    worker = ChatWorker(app.state.chat_settings, app.state.session_factory, runtime=object())
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(worker.claim) for _ in range(2)]
        jobs = [future.result(timeout=15) for future in futures]
    assert sum(job is not None for job in jobs) == 1
