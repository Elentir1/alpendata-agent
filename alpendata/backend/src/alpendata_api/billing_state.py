"""An authenticated Stripe read, never a browser return, changes paid access."""

from sqlalchemy import func, select

from .models import BillingAccount, Membership, now


def billing_access(db, organization_id):
    account = db.get(BillingAccount, organization_id)
    if account is None or account.status == "pilot":
        return True
    if account.status != "active" or account.access_until <= now():
        return False
    assigned = db.scalar(
        select(func.count())
        .select_from(Membership)
        .where(
            Membership.organization_id == organization_id,
            Membership.active.is_(True),
            Membership.licensed.is_(True),
        )
    )
    return assigned <= account.quantity


def reconcile(db, organization, account, gateway):
    subscriptions = gateway.subscriptions(account.customer_id)
    live = [s for s in subscriptions if s.get("status") not in {"canceled", "incomplete_expired"}]
    account.synced_at = now()
    if not subscriptions:
        if account.subscription_id:
            account.status, account.access_until = "review", 0
        return
    if len(live) > 1:
        account.status, account.access_until = "review", 0
        return
    subscription = live[0] if live else max(subscriptions, key=lambda s: s.get("created", 0))
    items = subscription.get("items") or {}
    rows = items.get("data") or []
    item = rows[0] if len(rows) == 1 else {}
    price = item.get("price") or {}
    quantity = item.get("quantity")
    invoice = subscription.get("latest_invoice") or {}
    valid = (
        subscription.get("customer") == account.customer_id
        and subscription.get("livemode") == account.livemode
        and (subscription.get("metadata") or {}).get("alpendata_organization") == organization.id
        and not items.get("has_more")
        and price.get("id") == gateway.settings.price_id
        and price.get("currency") == "chf"
        and type(quantity) is int
        and 1 <= quantity <= 1000
    )
    if not valid:
        account.status, account.access_until = "review", 0
        return
    account.subscription_id = subscription["id"]
    account.status = subscription["status"]
    account.quantity = quantity
    organization.seat_capacity = quantity
    account.cancel_at = subscription.get("cancel_at")
    period_end = item.get("current_period_end", 0)
    if subscription.get("cancel_at_period_end"):
        account.cancel_at = period_end
    # Active alone is insufficient for asynchronous payment methods or manual invoices.
    paid = isinstance(invoice, dict) and invoice.get("status") == "paid"
    account.access_until = period_end if account.status == "active" and paid else 0
    if account.cancel_at and account.access_until:
        account.access_until = min(account.access_until, account.cancel_at)


def billing_view(db, organization, account, configured):
    return {
        "configured": configured,
        "status": account.status if account else "pilot",
        "capacity": organization.seat_capacity,
        "assistant_available": billing_access(db, organization.id),
        "access_until": account.access_until if account else 0,
        "cancel_at": account.cancel_at if account else None,
        "synced_at": account.synced_at if account else None,
        "can_manage": bool(configured and account and account.customer_id),
    }
