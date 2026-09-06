"""Company billing authority and restart-safe hosted Checkout creation."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from .access import lock_organization, member
from .auth import authenticate, request_authorization
from .billing_gateway import BillingGateway, hosted_url
from .billing_state import billing_view, reconcile
from .models import BillingAccount, BillingCheckout, now
from .organizations import occupied_seats


class BillingLanguage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    language: Literal["fr", "en"] = "fr"


class CheckoutInput(BillingLanguage):
    request_id: UUID
    quantity: int = Field(ge=1, le=1000, strict=True)


def billing_router(settings, factory, gateway=None):
    router = APIRouter(prefix="/api")
    gateway = gateway or (BillingGateway(settings.billing) if settings.billing else None)

    def authorized(db, request, organization_id):
        user = authenticate(db, request_authorization(request, settings))
        organization = lock_organization(db, organization_id)
        member(db, user, organization_id, admin=True, licensed=False)
        return organization

    def configured(account=None):
        if gateway is None or settings.billing is None:
            raise HTTPException(503, "billing_not_configured")
        if account and account.livemode != settings.billing.livemode:
            raise HTTPException(409, "billing_environment_mismatch")

    def existing_checkout(account, attempt):
        if attempt.status in {"complete", "expired"}:
            return {"status": attempt.status}
        if attempt.session_id:
            session = gateway.session(attempt.session_id)
        elif now() - attempt.created_at >= 1800:
            session = gateway.recover_checkout(account, attempt)
            if session is None and now() >= attempt.created_at + 3600:
                # All sessions were read and the original fixed expiry is past:
                # even a late original creation can no longer succeed.
                attempt.status = "expired"
                return {"status": "expired"}
        else:
            return None
        if session:
            attempt.session_id, attempt.status = session["id"], session["status"]
        return session

    @router.get("/organizations/{organization_id}/billing")
    def get_billing(organization_id: str, request: Request):
        with factory.begin() as db:
            organization = authorized(db, request, organization_id)
            account = db.get(BillingAccount, organization_id)
            result = billing_view(db, organization, account, settings.billing is not None)
            latest = db.scalar(
                select(BillingCheckout)
                .where(
                    BillingCheckout.organization_id == organization_id,
                )
                .order_by(BillingCheckout.created_at.desc(), BillingCheckout.id.desc())
                .limit(1)
            )
            result["checkout"] = (
                {"request_id": latest.request_id, "quantity": latest.quantity, "language": latest.language}
                if latest and latest.status not in {"complete", "expired"}
                else None
            )
            return result

    @router.post("/organizations/{organization_id}/billing/refresh")
    def refresh(organization_id: str, request: Request):
        with factory.begin() as db:
            organization = authorized(db, request, organization_id)
            account = db.get(BillingAccount, organization_id)
            configured(account)
            if account and account.customer_id:
                reconcile(db, organization, account, gateway)
                db.flush()
            result = billing_view(db, organization, account, True)
            result["price"] = gateway.price()
            return result

    @router.post("/organizations/{organization_id}/billing/checkout")
    def checkout(organization_id: str, body: CheckoutInput, request: Request):
        # Reserve durable keys before ANY remote write. A rolled-back remote request
        # may already have succeeded; subsequent requests must reuse the same keys.
        with factory.begin() as db:
            organization = authorized(db, request, organization_id)
            account = db.get(BillingAccount, organization_id)
            configured(account)
            if account is None:
                account = BillingAccount(organization_id=organization_id, livemode=settings.billing.livemode)
                db.add(account)
                db.flush()
            attempt = db.scalar(
                select(BillingCheckout).where(
                    BillingCheckout.organization_id == organization_id,
                    BillingCheckout.request_id == str(body.request_id),
                )
            )
            if attempt and (attempt.quantity != body.quantity or attempt.language != body.language):
                raise HTTPException(409, "billing_request_conflict")
            if attempt is None:
                if account.customer_id:
                    reconcile(db, organization, account, gateway)
                    if account.status not in {"pilot", "canceled", "incomplete_expired"}:
                        raise HTTPException(409, "billing_subscription_exists")
                prior = db.scalars(
                    select(BillingCheckout).where(
                        BillingCheckout.organization_id == organization_id,
                    )
                ).all()
                for previous in prior:
                    session = existing_checkout(account, previous)
                    if session is None or session.get("status") == "open":
                        raise HTTPException(409, "billing_checkout_pending")
                if body.quantity < occupied_seats(db, organization_id):
                    raise HTTPException(409, "billing_seats_in_use")
                gateway.price()
                attempt = BillingCheckout(
                    organization_id=organization_id,
                    request_id=str(body.request_id),
                    quantity=body.quantity,
                    language=body.language,
                    price_id=settings.billing.price_id,
                )
                db.add(attempt)
                db.flush()
            attempt_id = attempt.id
        with factory.begin() as db:
            authorized(db, request, organization_id)
            account = db.get(BillingAccount, organization_id)
            attempt = db.get(BillingCheckout, attempt_id)
            if not account.customer_id:
                if now() - account.created_at >= 23 * 3600:
                    raise HTTPException(409, "billing_reconciliation_required")
                account.customer_id = gateway.customer(account)
        with factory.begin() as db:
            authorized(db, request, organization_id)
            account = db.get(BillingAccount, organization_id)
            attempt = db.get(BillingCheckout, attempt_id)
            session = existing_checkout(account, attempt)
            if session is None:
                if now() - attempt.created_at >= 1800:
                    raise HTTPException(409, "billing_reconciliation_required")
                session = gateway.checkout(account, attempt, settings.public_origin)
                attempt.session_id, attempt.status = session["id"], session["status"]
            if session.get("status") != "open":
                return {"status": session.get("status"), "url": None}
            return {"status": "open", "url": hosted_url(session.get("url"), "checkout.stripe.com")}

    @router.post("/organizations/{organization_id}/billing/portal")
    def portal(organization_id: str, body: BillingLanguage, request: Request):
        with factory.begin() as db:
            authorized(db, request, organization_id)
            account = db.get(BillingAccount, organization_id)
            configured(account)
            if not account or not account.customer_id:
                raise HTTPException(409, "billing_customer_required")
            return {"url": gateway.portal(account.customer_id, settings.public_origin, body.language)}

    def sync_customer(customer_id):
        with factory.begin() as db:
            account = db.scalar(select(BillingAccount).where(BillingAccount.customer_id == customer_id))
            if account:
                organization = lock_organization(db, account.organization_id)
                db.refresh(account)
                configured(account)
                reconcile(db, organization, account, gateway)

    @router.post("/billing/stripe/webhook")
    async def webhook(request: Request):
        configured()
        payload = bytearray()
        async for chunk in request.stream():
            payload.extend(chunk)
            if len(payload) > 1024 * 1024:
                raise HTTPException(413, "billing_event_too_large")
        event = gateway.event(bytes(payload), request.headers.get("stripe-signature", ""))
        if event.get("livemode") != settings.billing.livemode or event.get("account"):
            raise HTTPException(400, "billing_environment_mismatch")
        event_type = event.get("type", "")
        relevant = event_type.startswith("customer.subscription.") or event_type in {
            "invoice.paid",
            "invoice.payment_failed",
            "checkout.session.completed",
            "checkout.session.async_payment_succeeded",
            "checkout.session.async_payment_failed",
        }
        if relevant:
            customer_id = (event.get("data", {}).get("object") or {}).get("customer")
            if isinstance(customer_id, str):
                await run_in_threadpool(sync_customer, customer_id)
        # Duplicate and out-of-order events simply re-read current Stripe state.
        # The event body never supplies a seat count or binding to an organization.
        return {"received": True}

    return router
