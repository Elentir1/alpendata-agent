from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import select
from stripe_http import stripe_http

from alpendata_api.auth import issue_session
from alpendata_api.chat_worker import ChatWorker, authorize_job
from alpendata_api.model_gateway import ModelSettings
from alpendata_api.models import BillingAccount, BillingCheckout, User, now
from alpendata_api.runtime import RuntimeFailure, RuntimeSettings
from alpendata_api.settings import Settings


def actor(app, name):
    with app.state.session_factory.begin() as db:
        user = User(issuer="https://example.test", subject=name, display_name=name)
        db.add(user)
        db.flush()
        return user.id, {"Authorization": "Bearer " + issue_session(db, user, 3600)}


def test_checkout_restarts_keep_durable_keys_and_company_authority(database_url, service_factory):
    with stripe_http() as peer:
        settings = Settings(database_url, billing=peer.settings)
        with service_factory(settings, billing_gateway=peer.gateway) as (app, client):
            _, admin = actor(app, "admin")
            _, other = actor(app, "other")
            org = client.post("/api/organizations", headers=admin, json={"name": "Coaches"}).json()["id"]
            base = f"/api/organizations/{org}/billing"
            body = {"request_id": str(uuid4()), "quantity": 5, "language": "en"}
            assert client.post(base + "/checkout", json=body, headers=other).status_code == 404
            assert client.get(base, headers=other).status_code == 404
            assert not peer.received
            peer.fail_customer = True
            failed = client.post(base + "/checkout", json=body, headers=admin)
            assert failed.status_code == 502 and failed.json()["detail"] == "billing_unavailable"
            assert "Synthetic" not in failed.text
            assert (
                client.post(
                    base + "/checkout", json={**body, "request_id": str(uuid4())}, headers=admin
                ).status_code
                == 409
            )
            with app.state.session_factory() as db:
                saved = db.scalar(select(BillingCheckout))
                attempt_id = saved.id
                assert saved.session_id is None
        # Replace the actual application while the remote result is still uncertain.
        with service_factory(settings, billing_gateway=peer.gateway) as (app, client):
            peer.fail_checkout = True
            assert client.post(base + "/checkout", json=body, headers=admin).status_code == 502
            with ThreadPoolExecutor(max_workers=2) as pool:
                if app.state.engine.dialect.name == "postgresql":
                    responses = list(
                        pool.map(
                            lambda _: client.post(base + "/checkout", json=body, headers=admin), range(2)
                        )
                    )
                else:
                    responses = [client.post(base + "/checkout", json=body, headers=admin) for _ in range(2)]
            assert all(r.status_code == 200 for r in responses)
            assert responses[0].json() == responses[1].json()
            assert len(peer.sessions) == 1
            assert (
                client.post(base + "/checkout", json={**body, "language": "fr"}, headers=admin).status_code
                == 409
            )
            view = client.get(base, headers=admin).json()
            assert view["status"] == "pilot" and view["capacity"] == 3
            assert view["checkout"] == body
            assert not {"customer_id", "customer_key", "subscription_id"} & view.keys()
            assert client.post(base + "/portal", json={"language": "fr"}, headers=admin).status_code == 200
            assert client.post(base + "/portal", json={"language": "fr"}, headers=other).status_code == 404
            customers = [r for r in peer.received if r["path"] == "/v1/customers"]
            checkouts = [r for r in peer.received if r["path"] == "/v1/checkout/sessions"]
            assert (
                len(customers) == 2
                and customers[0]["headers"]["Idempotency-Key"] == customers[1]["headers"]["Idempotency-Key"]
            )
            assert len(checkouts) == 2
            assert all(
                r["headers"]["Idempotency-Key"] == "alpendata-checkout-" + attempt_id for r in checkouts
            )
            submitted = checkouts[-1]["body"]
            assert submitted["line_items[0][quantity]"] == ["5"]
            assert submitted["customer"] == ["cus_coaches"] and submitted["locale"] == ["en"]
            assert submitted["success_url"] == [settings.public_origin + "/?billing=return"]
            assert not any("payment_method_types" in k or "integration_identifier" in k for k in submitted)
            assert all("X-Stripe-Client-Telemetry" not in r["headers"] for r in peer.received)


@pytest.mark.linux_only
def test_signed_events_reconcile_paid_seats_and_revoke_real_worker_authority(
    database_url, service_factory, tmp_path
):
    with stripe_http() as peer:
        settings = Settings(
            database_url,
            billing=peer.settings,
            model=ModelSettings("mistral", "synthetic", "synthetic"),
            runtime=RuntimeSettings(tmp_path / "states", "sha256:" + "0" * 64),
        )
        with service_factory(settings, billing_gateway=peer.gateway) as (app, client):
            _, admin = actor(app, "admin")
            org = client.post("/api/organizations", headers=admin, json={"name": "Coaches"}).json()["id"]
            root = f"/api/organizations/{org}"
            base = root + "/billing"
            client.put(
                root + "/onboarding",
                headers=admin,
                json={"language": "fr", "role": "Coach", "needs": "Prepare meetings"},
            )
            conversation = client.post(
                root + "/chat/conversations", headers=admin, json={"language": "fr"}
            ).json()["id"]
            turn_path = root + "/chat/conversations/" + conversation + "/turns"
            client.post(
                turn_path, headers=admin, json={"request_id": str(uuid4()), "message": "My private task"}
            )
            worker = ChatWorker(settings, app.state.session_factory)
            job = worker.claim()
            assert job
            assert (
                client.post(
                    base + "/checkout", headers=admin, json={"request_id": str(uuid4()), "quantity": 5}
                ).status_code
                == 200
            )
            peer.subscribed(org, paid=False)
            webhook = "/api/billing/stripe/webhook"
            payload, headers = peer.signed()
            assert (
                client.post(webhook, content=payload, headers={"Stripe-Signature": "invalid"}).status_code
                == 400
            )
            old, old_headers = peer.signed(at=now() - 600)
            assert client.post(webhook, content=old, headers=old_headers).status_code == 400
            assert client.get(base, headers=admin).json()["status"] == "pilot"
            assert client.post(webhook, content=payload, headers=headers).status_code == 200
            assert (
                client.get(root + "/onboarding", headers=admin).json()["detail"] == "billing_access_required"
            )
            with app.state.session_factory.begin() as db:
                with pytest.raises(RuntimeFailure, match="agent_access_revoked"):
                    authorize_job(db, job)
            # The same event is now delivered after payment; its stale body has no authority.
            peer.subscribed(org, quantity=5)
            assert client.post(webhook, content=payload, headers=headers).status_code == 200
            assert client.get(base, headers=admin).json()["capacity"] == 5
            assert client.get(root + "/onboarding", headers=admin).status_code == 200
            with app.state.session_factory.begin() as db:
                authorize_job(db, job)
            peer.subscriptions[0]["status"] = "canceled"
            assert client.post(webhook, content=payload, headers=headers).status_code == 200
            assert not client.get(base, headers=admin).json()["assistant_available"]
            # Even an old paid event cannot revive a canceled subscription.
            paid, paid_headers = peer.signed(event_type="invoice.paid")
            assert client.post(webhook, content=paid, headers=paid_headers).status_code == 200
            worker.finish(job, result={"response": "Must not be delivered"})
            history = client.get(root + "/chat/conversations/" + conversation, headers=admin).json()
            assert history["turns"][0]["error_code"] == "agent_access_revoked"
            assert history["turns"][0]["response"] is None
            assert client.get(root + "/members", headers=admin).status_code == 200
            assert client.post(base + "/portal", headers=admin, json={}).status_code == 200
            with app.state.session_factory() as db:
                assert db.get(BillingAccount, org).status == "canceled"
