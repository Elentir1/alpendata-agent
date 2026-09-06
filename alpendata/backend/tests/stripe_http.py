"""A local HTTP Stripe peer; the application uses the unmodified official SDK."""

import hashlib
import hmac
import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import stripe

from alpendata_api.billing_gateway import API_VERSION, BillingGateway, BillingSettings, StripeSession
from alpendata_api.models import now


class StripePeer:
    def __init__(self):
        self.settings = BillingSettings(
            "rk_" + "test_synthetic", "whsec_" + "synthetic", "price_seats", "bpc_portal"
        )
        self.received, self.subscriptions, self.sessions = [], [], {}
        self.customers = {}
        self.fail_customer = self.fail_checkout = False
        self.portal = {
            "id": "bpc_portal",
            "object": "billing_portal.configuration",
            "active": True,
            "livemode": False,
            "features": {
                "subscription_update": {
                    "enabled": True,
                    "default_allowed_updates": ["quantity"],
                    "proration_behavior": "always_invoice",
                    "products": [{"product": "prod_seats", "prices": ["price_seats"]}],
                },
                "subscription_cancel": {"enabled": True, "mode": "at_period_end"},
            },
        }
        self.price = {
            "id": "price_seats",
            "object": "price",
            "active": True,
            "livemode": False,
            "currency": "chf",
            "billing_scheme": "per_unit",
            "unit_amount": 2300,
            "recurring": {"interval": "month", "interval_count": 1, "usage_type": "licensed"},
        }

    def customer(self, body, headers):
        key = headers["Idempotency-Key"]
        self.customers.setdefault(
            key, {"id": "cus_coaches" if not self.customers else "cus_duplicate", "object": "customer"}
        )
        if self.fail_customer:
            self.fail_customer = False
            return 500, {"error": {"type": "api_error", "message": "Synthetic lost customer response"}}
        return 200, self.customers[key]

    def checkout(self, body, headers):
        key = headers["Idempotency-Key"]
        if key not in self.sessions:
            self.sessions[key] = {
                "id": "cs_" + str(len(self.sessions)),
                "object": "checkout.session",
                "status": "open",
                "url": "https://checkout.stripe.com/c/pay/synthetic",
                "metadata": {"alpendata_checkout": body["metadata[alpendata_checkout]"][0]},
            }
        if self.fail_checkout:
            self.fail_checkout = False
            return 500, {"error": {"type": "api_error", "message": "Synthetic lost Checkout response"}}
        return 200, self.sessions[key]

    def handle(self, method, path, body, headers):
        self.received.append({"method": method, "path": path, "body": body, "headers": dict(headers)})
        handlers = {
            ("GET", "/v1/checkout/sessions"): lambda: (
                200,
                {"object": "list", "data": list(self.sessions.values()), "has_more": False},
            ),
            ("GET", "/v1/billing_portal/configurations/bpc_portal"): lambda: (200, self.portal),
            ("GET", "/v1/prices/price_seats"): lambda: (200, self.price),
            ("POST", "/v1/customers"): lambda: self.customer(body, headers),
            ("POST", "/v1/checkout/sessions"): lambda: self.checkout(body, headers),
            ("GET", "/v1/subscriptions"): lambda: (
                200,
                {"object": "list", "data": self.subscriptions, "has_more": False},
            ),
            ("POST", "/v1/billing_portal/sessions"): lambda: (
                200,
                {
                    "object": "billing_portal.session",
                    "id": "bps_test",
                    "url": "https://billing.stripe.com/p/session/synthetic",
                },
            ),
        }
        if (method, path) in handlers:
            return handlers[(method, path)]()
        if method == "GET" and path.startswith("/v1/checkout/sessions/"):
            return 200, next(s for s in self.sessions.values() if path.endswith("/" + s["id"]))
        return 404, {"error": {"type": "invalid_request_error", "message": "Unexpected local path"}}

    def subscribed(self, org, *, quantity=5, status="active", paid=True):
        self.subscriptions = [
            {
                "id": "sub_coaches",
                "object": "subscription",
                "customer": "cus_coaches",
                "created": now(),
                "livemode": False,
                "status": status,
                "metadata": {"alpendata_organization": org},
                "items": {
                    "data": [
                        {
                            "id": "si_seats",
                            "price": self.price,
                            "quantity": quantity,
                            "current_period_end": now() + 86400,
                        }
                    ],
                    "has_more": False,
                },
                "latest_invoice": {
                    "object": "invoice",
                    "id": "in_paid",
                    "status": "paid" if paid else "open",
                },
                "cancel_at_period_end": False,
                "cancel_at": None,
            }
        ]

    def signed(
        self,
        *,
        event_id="evt_synthetic",
        event_type="customer.subscription.updated",
        customer="cus_coaches",
        at=None,
        livemode=False,
    ):
        payload = json.dumps(
            {
                "id": event_id,
                "object": "event",
                "type": event_type,
                "created": now() - 3600,
                "livemode": livemode,
                "data": {"object": {"customer": customer, "quantity": 999, "status": "active"}},
            }
        ).encode()
        timestamp = now() if at is None else at
        digest = hmac.new(
            self.settings.webhook_secret.encode(), str(timestamp).encode() + b"." + payload, hashlib.sha256
        ).hexdigest()
        return payload, {"Stripe-Signature": f"t={timestamp},v1={digest}"}


@contextmanager
def stripe_http():
    peer = StripePeer()

    class Handler(BaseHTTPRequestHandler):
        def dispatch(self):
            content = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            parsed = urlsplit(self.path)
            body = parse_qs(content.decode() if self.command == "POST" else parsed.query)
            status, response = peer.handle(self.command, parsed.path, body, self.headers)
            encoded = json.dumps(response).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        do_GET = do_POST = dispatch

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    sdk = stripe.StripeClient(
        peer.settings.api_key,
        stripe_version=API_VERSION,
        max_network_retries=0,
        http_client=stripe.RequestsClient(timeout=5, session=StripeSession()),
        base_addresses={"api": f"http://127.0.0.1:{server.server_port}"},
    )
    peer.gateway = BillingGateway(peer.settings, client=sdk)
    try:
        yield peer
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
