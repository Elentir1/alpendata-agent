"""Password hashing and shared database admission, independent of Microsoft."""

import secrets
from threading import BoundedSemaphore

from cryptography.exceptions import InvalidKey
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
from fastapi import HTTPException
from sqlalchemy import case, delete, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .auth import token_digest
from .models import SignInLimit, now

HASH_SLOTS = BoundedSemaphore(2)


def hash_password(password):
    if not HASH_SLOTS.acquire(blocking=False):
        raise HTTPException(503, "password_service_busy", headers={"Retry-After": "2"})
    try:
        return Argon2id(
            salt=secrets.token_bytes(16), length=32, iterations=3, lanes=1, memory_cost=65536
        ).derive_phc_encoded(password.encode("utf-8"))
    finally:
        HASH_SLOTS.release()


DUMMY_HASH = hash_password(secrets.token_urlsafe(48))


def verify_password(password, encoded):
    if not HASH_SLOTS.acquire(blocking=False):
        raise HTTPException(503, "password_service_busy", headers={"Retry-After": "2"})
    try:
        Argon2id.verify_phc_encoded(password.encode("utf-8"), encoded or DUMMY_HASH)
        return encoded is not None
    except InvalidKey:
        return False
    finally:
        HASH_SLOTS.release()


def admit(factory, address, identity):
    """Charge every attempt before hashing; failed logins cannot roll back limits."""
    timestamp, retry = now(), 0
    with factory.begin() as db:
        db.execute(delete(SignInLimit).where(SignInLimit.reset_at < timestamp - 3600))
        insert = {"postgresql": pg_insert, "sqlite": sqlite_insert}[db.bind.dialect.name]
        # The IP is supplied by the server/proxy trust boundary, never a body/header lookup here.
        for scope, value, limit in (("ip", address, 40), ("identity", identity, 10)):
            key = token_digest(scope + ":" + value)
            db.execute(
                insert(SignInLimit)
                .values(key=key, attempts=0, reset_at=timestamp + 300)
                .on_conflict_do_nothing(index_elements=["key"])
            )
            expired = SignInLimit.reset_at <= timestamp
            attempts, reset = db.execute(
                update(SignInLimit)
                .where(SignInLimit.key == key)
                .values(
                    attempts=case((expired, 1), else_=SignInLimit.attempts + 1),
                    reset_at=case((expired, timestamp + 300), else_=SignInLimit.reset_at),
                )
                .returning(SignInLimit.attempts, SignInLimit.reset_at)
            ).one()
            if attempts > limit:
                retry = max(retry, reset - timestamp)
    if retry:
        raise HTTPException(429, "signin_rate_limited", headers={"Retry-After": str(retry)})
