"""Stripe's hosted payment pages; server-owned CHF price and return destination."""

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import requests
import stripe
from fastapi import HTTPException

API_VERSION = "2026-08-26.dahlia"
# Upstream attribution is opt-in. No integration_identifier or application tagging.
stripe.enable_telemetry = False


@dataclass(frozen=True)
class BillingSettings:
    api_key: str = field(repr=False)
    webhook_secret: str = field(repr=False)
    price_id: str
    portal_configuration_id: str

    def __post_init__(self):
        patterns = (
            (self.api_key, r"[rs]k_(test|live)_[A-Za-z0-9]+"),
            (self.webhook_secret, r"whsec_[A-Za-z0-9]+"),
            (self.price_id, r"price_[A-Za-z0-9]+"),
            (self.portal_configuration_id, r"bpc_[A-Za-z0-9]+"),
        )
        if any(not re.fullmatch(pattern, value) for value, pattern in patterns):
            raise ValueError("Billing requires Stripe credentials, a price and a portal configuration")

    @property
    def livemode(self):
        return "_live_" in self.api_key


class StripeSession(requests.Session):
    def request(self, method, url, **kwargs):
        # A redirect must not forward a payment request or credential elsewhere.
        with requests.Session() as session:
            session.trust_env = False
            kwargs["allow_redirects"] = False
            return session.request(method, url, **kwargs)


def hosted_url(value, host):
    parsed = urlsplit(value or "")
    if parsed.scheme != "https" or parsed.netloc != host or parsed.username or not parsed.path:
        raise HTTPException(502, "billing_response_invalid")
    return value


class BillingGateway:
    def __init__(self, settings, *, client=None):
        self.settings = settings
        self.client = client or stripe.StripeClient(
            settings.api_key,
            stripe_version=API_VERSION,
            max_network_retries=0,
            http_client=stripe.RequestsClient(timeout=15, session=StripeSession()),
        )

    def call(self, method, *args, **kwargs):
        try:
            return method(*args, **kwargs).to_dict()
        except stripe.StripeError:
            # Provider diagnostics can contain billing details; keep them off the public API.
            raise HTTPException(502, "billing_unavailable") from None

    def price(self):
        price = self.call(self.client.v1.prices.retrieve, self.settings.price_id)
        recurring = price.get("recurring") or {}
        if (
            price.get("id") != self.settings.price_id
            or price.get("livemode") != self.settings.livemode
            or not price.get("active")
            or price.get("currency") != "chf"
            or price.get("billing_scheme") != "per_unit"
            or type(price.get("unit_amount")) is not int
            or price["unit_amount"] <= 0
            or recurring.get("interval") != "month"
            or recurring.get("interval_count") != 1
            or recurring.get("usage_type") != "licensed"
            or price.get("transform_quantity")
        ):
            raise HTTPException(503, "billing_price_invalid")
        return {"currency": "chf", "unit_amount": price["unit_amount"], "interval": "month"}

    def customer(self, account):
        return self.call(
            self.client.v1.customers.create,
            {"metadata": {"alpendata_organization": account.organization_id}},
            options={"idempotency_key": "alpendata-customer-" + account.customer_key},
        )["id"]

    def checkout(self, account, attempt, origin):
        return self.call(
            self.client.v1.checkout.sessions.create,
            {
                "mode": "subscription",
                "customer": account.customer_id,
                "client_reference_id": account.organization_id,
                "metadata": {"alpendata_checkout": attempt.id},
                "line_items": [{"price": attempt.price_id, "quantity": attempt.quantity}],
                "locale": attempt.language,
                "success_url": origin + "/?billing=return",
                "cancel_url": origin + "/?billing=return",
                "expires_at": attempt.created_at + 3600,
                "subscription_data": {"metadata": {"alpendata_organization": account.organization_id}},
            },
            options={"idempotency_key": "alpendata-checkout-" + attempt.id},
        )

    def session(self, session_id):
        return self.call(self.client.v1.checkout.sessions.retrieve, session_id)

    def recover_checkout(self, account, attempt):
        result = self.call(
            self.client.v1.checkout.sessions.list, {"customer": account.customer_id, "limit": 100}
        )
        matches = [
            item
            for item in result["data"]
            if (item.get("metadata") or {}).get("alpendata_checkout") == attempt.id
        ]
        if result.get("has_more") or len(matches) > 1:
            raise HTTPException(409, "billing_reconciliation_required")
        return matches[0] if matches else None

    def subscriptions(self, customer_id):
        result = self.call(
            self.client.v1.subscriptions.list,
            {"customer": customer_id, "status": "all", "limit": 100, "expand": ["data.latest_invoice"]},
        )
        if result.get("has_more"):
            raise HTTPException(409, "billing_reconciliation_required")
        return result["data"]

    def portal(self, customer_id, origin, language):
        configuration = self.call(
            self.client.v1.billing_portal.configurations.retrieve, self.settings.portal_configuration_id
        )
        features = configuration.get("features") or {}
        update = features.get("subscription_update") or {}
        cancel = features.get("subscription_cancel") or {}
        prices = [price for product in update.get("products", []) for price in product.get("prices", [])]
        if (
            not configuration.get("active")
            or configuration.get("livemode") != self.settings.livemode
            or not update.get("enabled")
            or set(update.get("default_allowed_updates", [])) != {"quantity"}
            or update.get("proration_behavior") != "always_invoice"
            or prices != [self.settings.price_id]
            or not cancel.get("enabled")
            or cancel.get("mode") != "at_period_end"
        ):
            raise HTTPException(503, "billing_portal_invalid")
        result = self.call(
            self.client.v1.billing_portal.sessions.create,
            {
                "customer": customer_id,
                "configuration": self.settings.portal_configuration_id,
                "return_url": origin + "/?billing=return",
                "locale": language,
            },
        )
        return hosted_url(result.get("url"), "billing.stripe.com")

    def event(self, payload, signature):
        try:
            event = stripe.Webhook.construct_event(payload, signature, self.settings.webhook_secret)
            return event.to_dict()
        except (ValueError, stripe.SignatureVerificationError):
            raise HTTPException(400, "billing_signature_invalid") from None
