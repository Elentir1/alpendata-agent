"""Operator provisioning: give an activation link, never choose a client's password."""

import argparse
import json
import os
import secrets
from pathlib import Path
from uuid import UUID

from sqlalchemy import select, update

from .access import lock_organization
from .auth import token_digest
from .billing_state import billing_access
from .database import database_factory
from .health import database_ready, release_head
from .models import AuthSession, PasswordAccount, User, new_id, now
from .organizations import add_member, occupied_seats
from .schemas import InviteInput
from .settings import Settings


def activation(account):
    token = secrets.token_urlsafe(48)
    account.activation_hash = token_digest(token)
    account.activation_expires_at = now() + 86400
    return token


def provision(db, email, display_name, *, organization_id=None, role="member"):
    email = InviteInput(email=email).email
    display_name = display_name.strip()
    if not display_name or len(display_name) > 160 or role not in {"admin", "member"}:
        raise ValueError("account_input_invalid")
    if db.scalar(select(PasswordAccount).where(PasswordAccount.email == email)):
        raise ValueError("password_account_exists")
    if organization_id:
        organization_id = str(UUID(organization_id))
        organization = lock_organization(db, organization_id)
        if (
            not billing_access(db, organization_id)
            or occupied_seats(db, organization_id) >= organization.seat_capacity
        ):
            raise ValueError("no_available_license")
    user = User(issuer="alpendata:password", subject=new_id(), display_name=display_name)
    # Manual delivery is not an SMTP proof and never merges a Microsoft identity by email.
    db.add(user)
    db.flush()
    account = PasswordAccount(user_id=user.id, email=email)
    db.add(account)
    if organization_id:
        add_member(db, organization_id, user.id, role)
    token = activation(account)
    db.flush()
    return account, token


def reset(db, email):
    email = InviteInput(email=email).email
    account = db.scalar(select(PasswordAccount).where(PasswordAccount.email == email).with_for_update())
    if account is None or not db.get(User, account.user_id).active:
        raise ValueError("password_account_unavailable")
    account.password_hash = None
    db.execute(update(AuthSession).where(AuthSession.user_id == account.user_id).values(revoked=True))
    return account, activation(account)


def main():
    parser = argparse.ArgumentParser(
        description="Provision a pilot account or recover its access after verifying its owner."
    )
    parser.add_argument("operation", choices=["create", "reset"])
    parser.add_argument("--email", required=True)
    parser.add_argument("--name")
    parser.add_argument("--organization-id")
    parser.add_argument("--role", choices=["member", "admin"], default="member")
    parser.add_argument("--activation-file", required=True, type=Path)
    args = parser.parse_args()
    if args.operation == "create" and not args.name:
        parser.error("create requires --name")
    if args.operation == "reset" and (args.name or args.organization_id or args.role != "member"):
        parser.error("reset does not change names, memberships or roles")
    settings = Settings.from_environment()
    engine, factory = database_factory(settings.database_url)
    try:
        if not database_ready(engine, release_head()):
            raise ValueError("application_database_not_ready")
        destination = args.activation_file
        if not destination.is_absolute() or not destination.parent.is_dir():
            raise ValueError("activation_file_requires_existing_absolute_parent")
        # Exclusive creation refuses symlinks and existing files. Only a new file is written.
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            with factory.begin() as db:
                if args.operation == "create":
                    account, token = provision(
                        db, args.email, args.name, organization_id=args.organization_id, role=args.role
                    )
                else:
                    account, token = reset(db, args.email)
                output.write(settings.public_origin + "/#activation=" + token + "\n")
                output.flush()
                os.fsync(output.fileno())
                user_id = account.user_id
        print(json.dumps({"status": "activation_prepared", "user_id": user_id, "expires_in_seconds": 86400}))
    except Exception:
        # Never print database credentials, activation links or provider diagnostics.
        print(json.dumps({"status": "account_operation_failed"}))
        raise SystemExit(1) from None
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
