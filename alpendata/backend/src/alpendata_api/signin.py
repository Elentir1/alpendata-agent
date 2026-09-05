"""Browser authentication routes. Provider tokens never leave the server."""

import secrets
from typing import Annotated
from urllib.parse import parse_qsl

from cryptography.fernet import InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from requests import RequestException
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from .auth import BROWSER_COOKIE, SESSION_COOKIE, issue_session, require_origin, token_digest
from .microsoft_identity import MicrosoftSignIn
from .models import AuthSession, SignInFlow, User, now
from .settings import Settings
from .vault import Vault

FLOW_SECONDS = 600


async def callback_parameters(request: Request) -> dict:
    if request.headers.get("content-type", "").split(";", 1)[0] != "application/x-www-form-urlencoded":
        raise HTTPException(415, "invalid_signin_response")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 16384:
            raise HTTPException(413, "invalid_signin_response")
    try:
        fields = parse_qsl(body.decode("ascii"), strict_parsing=True, max_num_fields=10)
    except (UnicodeError, ValueError):
        raise HTTPException(400, "invalid_signin_response") from None
    params = dict(fields)
    if len(fields) != len(params):
        raise HTTPException(400, "invalid_signin_response")
    return params


def signin_router(settings: Settings, factory, provider: MicrosoftSignIn | None = None):
    router = APIRouter(prefix="/api/auth")
    vault = Vault(settings.credential_keys) if settings.microsoft_enabled else None
    provider = provider or MicrosoftSignIn(settings)

    def enabled():
        if vault is None:
            raise HTTPException(503, "microsoft_signin_not_configured")

    @router.get("/options")
    def options():
        return {"microsoft": settings.microsoft_enabled, "invitation_email": settings.smtp_enabled}

    @router.post("/microsoft/start")
    def start(request: Request):
        require_origin(request, settings)
        enabled()
        try:
            flow = provider.begin()
        except (ValueError, RequestException) as error:
            raise HTTPException(502, "microsoft_signin_unavailable") from error
        browser = secrets.token_urlsafe(48)
        state_hash = token_digest(flow["state"])
        with factory.begin() as db:
            db.execute(delete(SignInFlow).where(SignInFlow.expires_at <= now()))
            db.add(
                SignInFlow(
                    state_hash=state_hash,
                    browser_hash=token_digest(browser),
                    encrypted_flow=vault.seal("signin:" + state_hash, flow),
                    expires_at=now() + FLOW_SECONDS,
                )
            )
        response = JSONResponse({"authorization_url": flow["auth_uri"]})
        # Microsoft returns a cross-site top-level form POST. Only this short-lived
        # flow cookie uses SameSite=None; the authenticated session remains Lax.
        response.set_cookie(
            BROWSER_COOKIE, browser, secure=True, httponly=True, samesite="none", max_age=FLOW_SECONDS
        )
        return response

    @router.post("/microsoft/callback")
    def callback(request: Request, params: Annotated[dict, Depends(callback_parameters)]):
        enabled()
        state = params.get("state", "")
        browser = request.cookies.get(BROWSER_COOKIE, "")
        if not state or len(state) > 512 or not browser or len(browser) > 512:
            raise HTTPException(400, "invalid_signin_flow")
        digest = token_digest(state)
        # Consume in a separate committed transaction BEFORE exchanging the code.
        # Failure or replay can only start a new flow, never reuse this one.
        with factory.begin() as db:
            pending = db.scalar(select(SignInFlow).where(SignInFlow.state_hash == digest).with_for_update())
            if (
                pending is None
                or pending.expires_at <= now()
                or not secrets.compare_digest(pending.browser_hash, token_digest(browser))
            ):
                raise HTTPException(400, "invalid_signin_flow")
            encrypted = pending.encrypted_flow
            db.delete(pending)
        try:
            flow = vault.open("signin:" + digest, encrypted)
            identity = provider.complete(flow, params)
        except (InvalidToken, ValueError, RequestException) as error:
            raise HTTPException(401, "microsoft_signin_failed") from error
        with factory.begin() as db:
            query = select(User).where(User.issuer == identity.issuer, User.subject == identity.subject)
            user = db.scalar(query)
            if user is None:
                try:
                    with db.begin_nested():
                        user = User(
                            issuer=identity.issuer,
                            subject=identity.subject,
                            display_name=identity.display_name,
                        )
                        db.add(user)
                        db.flush()
                except IntegrityError:
                    # Another successful sign-in may have created the same identity.
                    user = db.scalar(query)
                    if user is None:
                        raise
            if not user.active:
                raise HTTPException(403, "account_disabled")
            user.display_name = identity.display_name
            previous = request.cookies.get(SESSION_COOKIE, "")
            if previous and len(previous) <= 512:
                old_session = db.get(AuthSession, token_digest(previous))
                if old_session is not None:
                    old_session.revoked = True
            token = issue_session(db, user, settings.session_lifetime_seconds)
        response = RedirectResponse(settings.public_origin + "/", status_code=303)
        response.set_cookie(
            SESSION_COOKIE,
            token,
            secure=True,
            httponly=True,
            samesite="lax",
            max_age=settings.session_lifetime_seconds,
        )
        response.delete_cookie(BROWSER_COOKIE, secure=True, httponly=True, samesite="none")
        return response

    return router
