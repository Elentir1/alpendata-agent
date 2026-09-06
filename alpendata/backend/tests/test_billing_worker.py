from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Event
from uuid import uuid4

import pytest
from stripe_http import stripe_http

from alpendata_api.billing_worker import BillingWorker
from alpendata_api.models import BillingAccount, now
from alpendata_api.settings import Settings


@pytest.fixture
def service(database_url, service_factory):
    with stripe_http() as peer:
        settings = Settings(database_url, billing=peer.settings)
        with service_factory(settings, billing_gateway=peer.gateway) as (app, client):
            app.state.billing_settings, app.state.stripe_peer = settings, peer
            yield app, client


def due(app, organization_id):
    with app.state.session_factory.begin() as db:
        db.get(BillingAccount, organization_id).next_sync_at = 0


def test_periodic_reads_renew_paid_access_without_webhooks_and_preserve_expiry_during_outage(
    service, account
):
    app, client = service
    _, admin = account("admin@example.com")
    org = client.post("/api/organizations", headers=admin, json={"name": "Coaches"}).json()["id"]
    base = f"/api/organizations/{org}/billing"
    peer = app.state.stripe_peer
    worker = BillingWorker(app.state.billing_settings, app.state.session_factory, gateway=peer.gateway)
    assert not worker.run_once()
    assert not peer.received
    assert (
        client.post(
            base + "/checkout", headers=admin, json={"request_id": str(uuid4()), "quantity": 4}
        ).status_code
        == 200
    )
    peer.subscribed(org, quantity=4)
    assert worker.run_once()
    receipt = client.get(base, headers=admin).json()
    assert receipt["capacity"] == 4 and receipt["assistant_available"]
    assert receipt["next_sync_at"] > now() and receipt["synced_at"]
    calls = len(peer.received)
    assert not worker.run_once() and len(peer.received) == calls
    peer.subscriptions[0]["items"]["data"][0]["current_period_end"] = receipt["access_until"] + 86400
    peer.subscriptions[0]["items"]["data"][0]["quantity"] = 6
    due(app, org)
    assert worker.run_once()
    renewed = client.get(base, headers=admin).json()
    assert renewed["access_until"] > receipt["access_until"] and renewed["capacity"] == 6
    reader = peer.subscription_reader
    peer.subscription_reader = lambda body: (
        503,
        {"error": {"type": "api_error", "message": "private-provider-diagnostic"}},
    )
    due(app, org)
    assert worker.run_once()
    failed = client.get(base, headers=admin).json()
    assert failed["sync_error"] == "billing_unavailable"
    assert (failed["access_until"], failed["synced_at"], failed["capacity"]) == (
        renewed["access_until"],
        renewed["synced_at"],
        renewed["capacity"],
    )
    assert failed["assistant_available"] and "private-provider-diagnostic" not in str(failed)
    restarted = BillingWorker(app.state.billing_settings, app.state.session_factory, gateway=peer.gateway)
    assert not restarted.run_once()
    peer.subscription_reader = reader
    peer.subscriptions[0]["status"] = "canceled"
    due(app, org)
    assert restarted.run_once()
    canceled = client.get(base, headers=admin).json()
    assert canceled["status"] == "canceled" and not canceled["assistant_available"]
    assert canceled["sync_error"] is None
    assert all(row["method"] == "GET" for row in peer.received[calls:])


@pytest.mark.linux_only
def test_two_reconcilers_skip_busy_company_and_back_off_failed_customer_without_starvation(service, account):
    app, client = service
    if app.state.engine.dialect.name != "postgresql":
        pytest.skip("Requires real PostgreSQL row locking")
    _, admin = account("admin@example.com")
    peer = app.state.stripe_peer
    organizations, subscriptions = [], {}
    for index in range(3):
        org = client.post("/api/organizations", headers=admin, json={"name": f"Coaches {index}"}).json()["id"]
        organizations.append(org)
        customer = f"cus_{index}"
        peer.subscribed(org, quantity=7)
        snapshot = deepcopy(peer.subscriptions)
        snapshot[0].update(customer=customer, id=f"sub_{index}")
        subscriptions[customer] = snapshot
        with app.state.session_factory.begin() as db:
            db.add(
                BillingAccount(
                    organization_id=org,
                    customer_id=customer,
                    subscription_id=f"sub_{index}",
                    status="active",
                    access_until=now() + 3600,
                    quantity=3,
                    livemode=index == 2,
                    next_sync_at=index,
                )
            )
    entered, release = Event(), Event()

    def respond(body):
        customer = body["customer"][0]
        if customer == "cus_0":
            entered.set()
            assert release.wait(30)
            return 503, {"error": {"type": "api_error", "message": "private-provider-diagnostic"}}
        return 200, {"object": "list", "data": subscriptions[customer], "has_more": False}

    peer.subscription_reader = respond
    first = BillingWorker(app.state.billing_settings, app.state.session_factory, gateway=peer.gateway)
    second = BillingWorker(app.state.billing_settings, app.state.session_factory, gateway=peer.gateway)
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(first.run_once)
        try:
            assert entered.wait(20)
            other = pool.submit(second.run_once)
            assert other.result(timeout=10)
            assert not pending.done()
        finally:
            release.set()
        assert pending.result(timeout=10)
    assert not first.run_once()
    with app.state.session_factory() as db:
        failed = db.get(BillingAccount, organizations[0])
        successful = db.get(BillingAccount, organizations[1])
        excluded = db.get(BillingAccount, organizations[2])
        assert failed.sync_error == "billing_unavailable" and failed.quantity == 3
        assert failed.next_sync_at > now() and failed.access_until > now()
        assert successful.quantity == 7 and successful.synced_at and successful.sync_error is None
        assert excluded.synced_at is None and excluded.next_sync_at == 2
    assert [r["body"]["customer"][0] for r in peer.received] == ["cus_0", "cus_1"]
