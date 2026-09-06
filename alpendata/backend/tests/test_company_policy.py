from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Event

import pytest
from test_microsoft_connections import connected_service as connected_service
from test_microsoft_connections import start
from test_routines import routine_service as routine_service
from test_schedules import activation, make_due
from test_schedules import approved_trial as approved_trial
from test_sharepoint_documents import download_service as download_service
from test_sharepoint_saves import permit
from test_sharepoint_saves import save_service as save_service

from alpendata_api.microsoft_data import CALLBACK
from alpendata_api.models import Conversation, now
from alpendata_api.organization_policy import CAPABILITIES
from alpendata_api.schedule_worker import ScheduleWorker


def test_company_rules_restrict_personal_consent_and_reviewed_writes_without_exposing_private_content(
    save_service,
):
    service, http, payload, conversation_path = save_service
    app, client, _, provider, _, org, alice, bob = service
    permit(service)
    base = f"/api/organizations/{org}"
    path = base + "/policy"
    original = client.get(path, headers=bob[2]).json()
    body = {"version": original["version"], "allowed_capabilities": ["mail", "calendar", "files"]}
    prepared = client.post(base + "/sharepoint/saves", headers=bob[2], json=payload).json()
    pending_consent = start(client, provider.http_client, org, bob, capabilities=("files", "files_write"))
    assert client.put(path, headers=bob[2], json=body).status_code == 403
    policy = client.put(path, headers=alice[2], json=body)
    assert policy.status_code == 200, policy.text
    assert client.post(CALLBACK, data=pending_consent, follow_redirects=False).status_code == 403
    assert set(policy.json()) == {"version", "allowed_capabilities", "updated_by", "updated_at"}
    assert client.put(path, headers=alice[2], json=body).status_code == 409
    assert (
        client.post(
            base + "/microsoft/connect", headers=bob[2], json={"capabilities": ["files_write"]}
        ).status_code
        == 403
    )
    connection = client.get(base + "/microsoft", headers=bob[2]).json()
    assert connection["restricted_capabilities"] == ["files_write"]
    assert "files_write" not in connection["capabilities"]
    confirm_path = base + "/sharepoint/saves/" + prepared["id"] + "/confirm"
    result = client.post(confirm_path, headers=bob[2], json={}).json()
    assert result["status"] == "failed" and result["error_code"] == "company_policy_denied"
    assert http.writes == []
    with app.state.session_factory() as db:
        old = db.get(Conversation, conversation_path.rsplit("/", 1)[1])
        old_prompt, old_capabilities = old.system_prompt, old.capabilities
    policy = client.put(
        path,
        headers=alice[2],
        json={"version": policy.json()["version"], "allowed_capabilities": ["calendar"]},
    ).json()
    before = len(http.calls)
    assert (
        client.post(base + "/microsoft/files/search", headers=bob[2], json={"query": "coaching"}).status_code
        == 403
    )
    assert client.get(base + "/microsoft/mail", headers=alice[2]).status_code == 403
    assert len(http.calls) == before
    new = client.post(base + "/chat/conversations", headers=bob[2], json={"language": "en"}).json()
    with app.state.session_factory() as db:
        old = db.get(Conversation, conversation_path.rsplit("/", 1)[1])
        assert (old.system_prompt, old.capabilities) == (old_prompt, old_capabilities)
        assert db.get(Conversation, new["id"]).capabilities == []
    assert client.get(conversation_path, headers=alice[2]).status_code == 404
    restored = client.put(
        path,
        headers=alice[2],
        json={"version": policy["version"], "allowed_capabilities": list(CAPABILITIES)},
    )
    assert restored.status_code == 200
    assert "files_write" in client.get(base + "/microsoft", headers=bob[2]).json()["capabilities"]
    assert client.post(confirm_path, headers=bob[2], json={}).json()["status"] == "failed"
    assert http.writes == []
    other = client.post("/api/organizations", headers=alice[2], json={"name": "Another company"}).json()["id"]
    assert client.get(f"/api/organizations/{other}/policy", headers=bob[2]).status_code == 404
    assert client.get(f"/api/organizations/{other}/policy", headers=alice[2]).json()["version"] == 0


@pytest.mark.linux_only
def test_policy_commit_waits_for_personal_reads_and_blocks_scheduled_runs(
    routine_service, approved_trial, request
):
    if not request.config.getoption("--postgresql-bin"):
        pytest.skip("Requires real PostgreSQL row locks")
    app, client, settings, _, graph, org, alice, bob = routine_service
    trial, worker = approved_trial
    base = f"/api/organizations/{org}"
    schedule = client.post(base + "/schedules", headers=bob[2], json=activation(trial)).json()
    make_due(app, schedule["id"], now() - 1)
    assert ScheduleWorker(settings, app.state.session_factory).tick() == 1
    started, release = Event(), Event()
    transport = graph.session

    class WaitingHTTP:
        def request(self, method, url, **kwargs):
            started.set()
            assert release.wait(15)
            return transport.request(method, url, **kwargs)

    graph.session = WaitingHTTP()
    try:
        with ThreadPoolExecutor(2) as pool:
            reading = pool.submit(client.get, base + "/microsoft/mail", headers=bob[2])
            assert started.wait(10)
            changing = pool.submit(
                client.put,
                base + "/policy",
                headers=alice[2],
                json={"version": 0, "allowed_capabilities": ["files"]},
            )
            with pytest.raises(TimeoutError):
                changing.result(timeout=2)
            release.set()
            assert reading.result(timeout=15).status_code == 200
            policy = changing.result(timeout=15)
            assert policy.status_code == 200, policy.text
    finally:
        release.set()
        graph.session = transport
    before = len(transport.calls)
    assert client.get(base + "/microsoft/mail", headers=bob[2]).status_code == 403
    assert len(transport.calls) == before
    blocked = client.get(base + "/schedules", headers=bob[2]).json()["schedules"][0]
    assert blocked["status"] == "blocked" and blocked["reason_code"] == "company_policy_denied"
    assert blocked["next_run_at"] is None
    assert worker.claim() is None
    assert ScheduleWorker(settings, app.state.session_factory).tick() == 0
    assert client.get(base + "/schedules", headers=alice[2]).json()["schedules"] == []
    restored = client.put(
        base + "/policy",
        headers=alice[2],
        json={"version": policy.json()["version"], "allowed_capabilities": list(CAPABILITIES)},
    )
    assert restored.status_code == 200
    assert client.get(base + "/schedules", headers=bob[2]).json()["schedules"][0]["status"] == "blocked"
