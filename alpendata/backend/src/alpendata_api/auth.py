"""Opaque sessions: only the trusted sign-in service can issue them.

No request header or body can create an identity or assign an administrator role.
"""

import hashlib
import secrets

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from .models import AuthSession, User, now
from .settings import Settings

SESSION_COOKIE = "__Host-alpendata_session"
BROWSER_COOKIE = "__Host-alpendata_signin"


def require_origin(request: Request, settings: Settings):
    if request.headers.get("origin") != settings.public_origin:
        raise HTTPException(403, "request_origin_not_allowed")


def request_authorization(request: Request, settings: Settings) -> str | None:
    authorization = request.headers.get("authorization")
    if authorization is not None:
        return authorization
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            require_origin(request, settings)
        return f"Bearer {token}"
    return None


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_session(db: Session, user: User, lifetime_seconds: int) -> str:
    if not user.active or lifetime_seconds < 1:
        raise ValueError("Cannot issue this session")
    token = secrets.token_urlsafe(48)
    db.add(
        AuthSession(
            token_hash=token_digest(token),
            user_id=user.id,
            expires_at=now() + lifetime_seconds,
        )
    )
    db.flush()
    return token


def authenticate(db: Session, authorization: str | None) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "authentication_required", headers={"WWW-Authenticate": "Bearer"})
    token = authorization.removeprefix("Bearer ")
    if not token or len(token) > 512:
        raise HTTPException(401, "invalid_session")
    session = db.get(AuthSession, token_digest(token))
    if session is None or session.revoked or session.expires_at <= now():
        raise HTTPException(401, "invalid_session")
    user = db.get(User, session.user_id)
    if user is None or not user.active:
        raise HTTPException(401, "invalid_session")
    return user
