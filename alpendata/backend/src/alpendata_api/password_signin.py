"""Login and owner-chosen passwords for manually provisioned pilot accounts."""

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import ConfigDict, Field, SecretStr
from sqlalchemy import select, update

from .auth import (
    SESSION_COOKIE,
    authenticate,
    issue_session,
    request_authorization,
    require_origin,
    token_digest,
)
from .models import AuthSession, PasswordAccount, User, now
from .passwords import admit, hash_password, verify_password
from .schemas import Input, InviteInput


class Login(InviteInput):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    password: SecretStr = Field(min_length=1, max_length=128)


class Activate(Input):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    token: SecretStr = Field(min_length=32, max_length=512)
    password: SecretStr = Field(min_length=15, max_length=128)


class ChangePassword(Input):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    current_password: SecretStr = Field(min_length=1, max_length=128)
    password: SecretStr = Field(min_length=15, max_length=128)


def session_response(db, user, settings, request, *, revoke_all=False):
    if revoke_all:
        db.execute(update(AuthSession).where(AuthSession.user_id == user.id).values(revoked=True))
    else:
        previous = request.cookies.get(SESSION_COOKIE, "")
        if previous:
            db.execute(
                update(AuthSession)
                .where(AuthSession.token_hash == token_digest(previous))
                .values(revoked=True)
            )
    token = issue_session(db, user, settings.session_lifetime_seconds)
    response = Response(status_code=204)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        secure=True,
        httponly=True,
        samesite="lax",
        max_age=settings.session_lifetime_seconds,
    )
    return response


def password_router(settings, factory):
    router = APIRouter(prefix="/api/auth/password")

    def admission(request, identity):
        require_origin(request, settings)
        admit(factory, request.client.host if request.client else "unknown", identity)

    @router.post("/login", status_code=204)
    def login(body: Login, request: Request):
        admission(request, body.email)
        with factory.begin() as db:
            account = db.scalar(
                select(PasswordAccount).where(PasswordAccount.email == body.email).with_for_update()
            )
            valid = verify_password(
                body.password.get_secret_value(), account.password_hash if account else None
            )
            user = db.get(User, account.user_id) if account else None
            if not valid or user is None or not user.active:
                raise HTTPException(401, "invalid_credentials")
            # Also fence password resets on SQLite, which has no row-level FOR UPDATE.
            if (
                db.execute(
                    update(PasswordAccount)
                    .where(
                        PasswordAccount.user_id == account.user_id,
                        PasswordAccount.password_hash == account.password_hash,
                    )
                    .values(password_hash=account.password_hash)
                ).rowcount
                != 1
            ):
                raise HTTPException(401, "invalid_credentials")
            return session_response(db, user, settings, request)

    @router.post("/activate", status_code=204)
    def activate(body: Activate, request: Request):
        digest = token_digest(body.token.get_secret_value())
        admission(request, "activation:" + digest)
        with factory.begin() as db:
            account = db.scalar(
                select(PasswordAccount).where(PasswordAccount.activation_hash == digest).with_for_update()
            )
            if account is None or not account.activation_expires_at or account.activation_expires_at <= now():
                raise HTTPException(400, "activation_invalid")
            user = db.get(User, account.user_id)
            if not user.active:
                raise HTTPException(400, "activation_invalid")
            encoded = hash_password(body.password.get_secret_value())
            if (
                db.execute(
                    update(PasswordAccount)
                    .where(
                        PasswordAccount.user_id == account.user_id,
                        PasswordAccount.activation_hash == digest,
                        PasswordAccount.activation_expires_at > now(),
                    )
                    .values(password_hash=encoded, activation_hash=None, activation_expires_at=None)
                ).rowcount
                != 1
            ):
                raise HTTPException(400, "activation_invalid")
            return session_response(db, user, settings, request, revoke_all=True)

    @router.post("/change", status_code=204)
    def change(body: ChangePassword, request: Request):
        require_origin(request, settings)
        with factory.begin() as db:
            user = authenticate(db, request_authorization(request, settings))
            # Separate committed admission cannot be rolled back by a bad current password.
            admission(request, "change:" + user.id)
            account = db.scalar(
                select(PasswordAccount).where(PasswordAccount.user_id == user.id).with_for_update()
            )
            if account is None or not verify_password(
                body.current_password.get_secret_value(), account.password_hash
            ):
                raise HTTPException(401, "invalid_credentials")
            encoded = hash_password(body.password.get_secret_value())
            if (
                db.execute(
                    update(PasswordAccount)
                    .where(
                        PasswordAccount.user_id == account.user_id,
                        PasswordAccount.password_hash == account.password_hash,
                    )
                    .values(password_hash=encoded, activation_hash=None, activation_expires_at=None)
                ).rowcount
                != 1
            ):
                raise HTTPException(401, "invalid_credentials")
            return session_response(db, user, settings, request, revoke_all=True)

    return router
