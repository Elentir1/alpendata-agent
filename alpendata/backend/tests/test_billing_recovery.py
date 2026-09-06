from uuid import uuid4

from sqlalchemy import select
from stripe_http import stripe_http
from test_billing import actor

from alpendata_api.backup_restore import suspend_restored_work
from alpendata_api.billing_state import billing_access
from alpendata_api.models import BillingAccount, BillingCheckout, Membership, now
from alpendata_api.organizations import add_member
from alpendata_api.settings import Settings


def test_lost_checkout_is_found_after_restart_and_expired_requests_do_not_create_another_subscription(
    database_url, service_factory
):
    with stripe_http() as peer:
        with service_factory(Settings(database_url, billing=peer.settings), billing_gateway=peer.gateway) as (
            app,
            client,
        ):
            _, admin = actor(app, "admin")
            org = client.post("/api/organizations", headers=admin, json={"name": "Coaches"}).json()["id"]
            base = f"/api/organizations/{org}/billing"
            body = {"request_id": str(uuid4()), "quantity": 4}
            peer.fail_checkout = True
            assert client.post(base + "/checkout", headers=admin, json=body).status_code == 502
            with app.state.session_factory.begin() as db:
                attempt = db.scalar(select(BillingCheckout))
                attempt.created_at = now() - 4000
            next(iter(peer.sessions.values()))["status"] = "expired"
            resumed = client.post(base + "/checkout", headers=admin, json=body)
            assert resumed.json() == {"status": "expired", "url": None}
            assert client.get(base, headers=admin).json()["checkout"] is None
            assert (
                len(
                    [
                        r
                        for r in peer.received
                        if r["method"] == "POST" and r["path"] == "/v1/checkout/sessions"
                    ]
                )
                == 1
            )
            assert (
                client.post(
                    base + "/checkout", headers=admin, json={**body, "request_id": str(uuid4())}
                ).status_code
                == 200
            )
            assert len(peer.customers) == 1 and len(peer.sessions) == 2
            peer.price["currency"] = "usd"
            assert (
                client.post(base + "/refresh", headers=admin, json={}).json()["detail"]
                == "billing_price_invalid"
            )
            before = len([r for r in peer.received if r["path"] == "/v1/billing_portal/sessions"])
            peer.portal["features"]["subscription_update"]["proration_behavior"] = "none"
            assert (
                client.post(base + "/portal", headers=admin, json={}).json()["detail"]
                == "billing_portal_invalid"
            )
            assert len([r for r in peer.received if r["path"] == "/v1/billing_portal/sessions"]) == before


def test_reduced_paid_capacity_keeps_admin_control_and_restored_receipts_need_fresh_stripe_confirmation(
    database_url, service_factory
):
    with stripe_http() as peer:
        with service_factory(Settings(database_url, billing=peer.settings), billing_gateway=peer.gateway) as (
            app,
            client,
        ):
            _, admin = actor(app, "admin")
            colleague_id, colleague = actor(app, "colleague")
            org = client.post("/api/organizations", headers=admin, json={"name": "Coaches"}).json()["id"]
            root = f"/api/organizations/{org}"
            with app.state.session_factory.begin() as db:
                add_member(db, org, colleague_id, "member")
            assert (
                client.post(
                    root + "/billing/checkout",
                    headers=colleague,
                    json={"request_id": str(uuid4()), "quantity": 2},
                ).status_code
                == 403
            )
            assert (
                client.post(
                    root + "/billing/checkout",
                    headers=admin,
                    json={"request_id": str(uuid4()), "quantity": 2},
                ).status_code
                == 200
            )
            peer.subscribed(org, quantity=1)
            payload, headers = peer.signed()
            assert (
                client.post("/api/billing/stripe/webhook", content=payload, headers=headers).status_code
                == 200
            )
            assert client.get(root + "/onboarding", headers=admin).status_code == 403
            assert client.get(root + "/members", headers=admin).status_code == 200
            with app.state.session_factory() as db:
                version = db.get(Membership, (org, colleague_id)).version
            assert (
                client.patch(
                    root + "/members/" + colleague_id,
                    headers=admin,
                    json={"version": version, "role": "member", "active": True, "licensed": False},
                ).status_code
                == 200
            )
            assert client.get(root + "/onboarding", headers=admin).status_code == 200
            with app.state.session_factory.begin() as db:
                db.get(BillingAccount, org).access_until = now() - 1
            assert client.get(root + "/onboarding", headers=admin).status_code == 403
            assert client.post(root + "/billing/refresh", headers=admin, json={}).json()[
                "assistant_available"
            ]
            suspend_restored_work(app.state.session_factory)
            with app.state.session_factory() as db:
                assert not billing_access(db, org)
                assert db.get(BillingAccount, org).status == "review"
            # Webhooks do not use the restored (revoked) browser sessions.
            assert (
                client.post("/api/billing/stripe/webhook", content=payload, headers=headers).status_code
                == 200
            )
            with app.state.session_factory() as db:
                assert billing_access(db, org)
