"""Reconcile bound Stripe customers without relying on webhook delivery."""

from fastapi import HTTPException
from sqlalchemy import select

from .billing_gateway import BillingGateway
from .billing_state import SYNC_INTERVAL, reconcile
from .models import BillingAccount, Organization, now
from .worker_service import event


class BillingWorker:
    def __init__(self, settings, factory, *, gateway=None):
        if settings.billing is None:
            raise ValueError("Billing requires Stripe settings")
        self.settings, self.factory = settings, factory
        self.gateway = gateway or BillingGateway(settings.billing)

    def run_once(self):
        with self.factory.begin() as db:
            organization = db.scalar(
                select(Organization)
                .join(BillingAccount, BillingAccount.organization_id == Organization.id)
                .where(
                    BillingAccount.customer_id.is_not(None),
                    BillingAccount.livemode == self.settings.billing.livemode,
                    BillingAccount.next_sync_at <= now(),
                )
                .order_by(BillingAccount.next_sync_at, Organization.id)
                .with_for_update(of=Organization, skip_locked=True)
                .limit(1)
            )
            if organization is None:
                return False
            account = db.get(BillingAccount, organization.id)
            # The same organization lock serializes webhooks, admin refreshes and
            # workers. A second worker skips an admitted customer instead of waiting.
            if account.next_sync_at > now():
                return False
            try:
                with db.begin_nested():
                    reconcile(db, organization, account, self.gateway)
            except HTTPException as error:
                account.sync_error = (
                    "billing_reconciliation_required"
                    if error.detail == "billing_reconciliation_required"
                    else "billing_unavailable"
                )
            except (KeyError, TypeError, ValueError):
                account.sync_error = "billing_response_invalid"
            account.next_sync_at = now() + SYNC_INTERVAL
            if account.sync_error:
                # Preserve the last successful access receipt and its original
                # expiry. A transient provider error neither grants nor extends it.
                event("billing", "sync_failed")
            return True


def main():
    from .worker_service import main as service_main

    return service_main("billing")


if __name__ == "__main__":
    raise SystemExit(main())
