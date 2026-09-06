"""Microsoft consent and reads always resolve the authenticated user's connection."""

import secrets
from typing import Annotated, Literal

from cryptography.fernet import InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field
from requests import RequestException
from sqlalchemy import delete, select

from .access import member
from .auth import authenticate, request_authorization, token_digest
from .graph import GraphError, GraphReader
from .graph_documents import content_download
from .microsoft_data import CALLBACK, MicrosoftData
from .microsoft_identity import MicrosoftIdentity
from .models import (
    AuthSession,
    Membership,
    MicrosoftConnection,
    MicrosoftConnectionFlow,
    Onboarding,
    User,
    now,
)
from .organization_policy import allowed_capabilities, require_allowed
from .schedule_state import block_owner_schedules
from .settings import Settings
from .signin import FLOW_SECONDS, callback_parameters
from .vault import Vault

CONNECT_COOKIE = "__Host-alpendata_connect"
PREFIX = "/api/organizations/{organization_id}/microsoft"


class ConnectInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    capabilities: list[Literal["mail", "calendar", "files", "files_write", "mail_send"]] = Field(
        min_length=1, max_length=5
    )


class SearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    query: str = Field(min_length=1, max_length=256)


def lock_member(db, user, organization_id, *, licensed=True):
    # Same row updated when an administrator removes access. Lock it before the
    # connection so deactivation cannot race credential use or connection creation.
    db.scalar(
        select(Membership)
        .where(
            Membership.organization_id == organization_id,
            Membership.user_id == user.id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return member(db, user, organization_id, licensed=licensed)


def connection_for(db, user, organization_id):
    return db.scalar(
        select(MicrosoftConnection)
        .where(
            MicrosoftConnection.organization_id == organization_id,
            MicrosoftConnection.owner_id == user.id,
        )
        .with_for_update()
    )


def context(connection):
    return f"microsoft:{connection.organization_id}:{connection.owner_id}:{connection.id}"


def clear_connection(connection, status="disconnected"):
    connection.generation += 1
    connection.status = status
    connection.encrypted_cache = None
    connection.capabilities = []
    connection.connected_at = None


def pending_actor(db, pending):
    session = db.get(AuthSession, pending.session_hash)
    if (
        session is None
        or session.revoked
        or session.expires_at <= now()
        or session.user_id != pending.owner_id
    ):
        raise HTTPException(401, "invalid_session")
    user = db.get(User, session.user_id)
    if user is None or not user.active:
        raise HTTPException(401, "invalid_session")
    lock_member(db, user, pending.organization_id)
    connection = connection_for(db, user, pending.organization_id)
    if (
        connection is None
        or connection.id != pending.connection_id
        or connection.generation != pending.generation
    ):
        raise HTTPException(409, "microsoft_connection_changed")
    return user, connection


class MicrosoftReader:
    def __init__(self, settings: Settings, factory, provider=None, graph=None):
        self.factory = factory
        self.vault = Vault(settings.credential_keys) if settings.microsoft_enabled else None
        self.provider, self.graph = provider or MicrosoftData(settings), graph or GraphReader()

    def read(self, organization_id, authorize, capability, *, operation="read", **arguments):
        def perform(graph, token):
            operations = {"mail": graph.mail, "calendar": graph.calendar, "files": graph.files}
            if operation == "download" and capability == "files":
                return content_download(graph, token, **arguments)
            if operation == "read" and capability in operations:
                return operations[capability](token, **arguments)
            raise GraphError(400, "agent_tool_arguments_invalid")

        return self.execute(organization_id, authorize, capability, perform)

    def execute(self, organization_id, authorize, capability, perform):
        """Authorize is a server callback, resolved again inside the credential transaction."""
        if self.vault is None:
            raise HTTPException(503, "microsoft_signin_not_configured")
        failure, result = None, None
        with self.factory.begin() as db:
            user = authorize(db)
            lock_member(db, user, organization_id)
            require_allowed(db, organization_id, [capability])
            connection = connection_for(db, user, organization_id)
            if connection is None or connection.status != "connected":
                raise HTTPException(409, "microsoft_reconnect_required")
            if capability not in connection.capabilities:
                raise HTTPException(403, "microsoft_permission_required")
            try:
                serialized = self.vault.open(context(connection), connection.encrypted_cache)["cache"]
                token, updated = self.provider.access(
                    serialized, MicrosoftIdentity(user.issuer, user.subject, user.display_name), capability
                )
                if not token:
                    raise GraphError(409, "microsoft_reconnect_required")
                connection.encrypted_cache = self.vault.seal(context(connection), {"cache": updated})
                result = perform(self.graph, token)
            except (InvalidToken, KeyError):
                failure = GraphError(409, "microsoft_reconnect_required")
            except RequestException:
                failure = GraphError(502, "microsoft_read_failed")
            except GraphError as error:
                failure = error
            if failure and failure.code == "microsoft_reconnect_required":
                clear_connection(connection, "reconnect_required")
                block_owner_schedules(db, organization_id, user.id, "microsoft_reconnect_required")
        # Persist cache refresh/revocation even when the operation returns an error.
        if failure:
            headers = {"Retry-After": str(failure.retry_after)} if failure.retry_after else None
            raise HTTPException(failure.status, failure.code, headers=headers)
        return result


def microsoft_router(settings: Settings, factory, provider=None, graph=None):
    router = APIRouter()
    vault = Vault(settings.credential_keys) if settings.microsoft_enabled else None
    provider = provider or MicrosoftData(settings)
    graph = graph or GraphReader()
    reader = MicrosoftReader(settings, factory, provider, graph)

    def enabled():
        if vault is None:
            raise HTTPException(503, "microsoft_signin_not_configured")

    def actor(db, request, organization_id, *, licensed=True):
        authorization = request_authorization(request, settings)
        user = authenticate(db, authorization)
        lock_member(db, user, organization_id, licensed=licensed)
        return user, token_digest(authorization.removeprefix("Bearer "))

    @router.get(PREFIX)
    def status(organization_id: str, request: Request):
        with factory.begin() as db:
            user, _ = actor(db, request, organization_id, licensed=False)
            connection = connection_for(db, user, organization_id)
            allowed = allowed_capabilities(db, organization_id)
            return {
                "available": settings.microsoft_enabled,
                "status": connection.status if connection else "disconnected",
                "capabilities": [item for item in connection.capabilities if item in allowed]
                if connection
                else [],
                "allowed_capabilities": allowed,
                "restricted_capabilities": [item for item in connection.capabilities if item not in allowed]
                if connection
                else [],
                "connected_at": connection.connected_at if connection else None,
            }

    @router.post(PREFIX + "/connect")
    def connect(organization_id: str, request: Request, body: ConnectInput):
        enabled()
        with factory.begin() as db:
            user, session_hash = actor(db, request, organization_id)
            require_allowed(db, organization_id, body.capabilities)
            connection = connection_for(db, user, organization_id)
            if connection is None:
                connection = MicrosoftConnection(organization_id=organization_id, owner_id=user.id)
                db.add(connection)
                db.flush()
            try:
                flow = provider.begin_connection(
                    list(dict.fromkeys(body.capabilities)),
                    MicrosoftIdentity(user.issuer, user.subject, user.display_name),
                )
            except (ValueError, RequestException):
                raise HTTPException(502, "microsoft_signin_unavailable") from None
            connection.generation += 1
            digest = token_digest(flow["state"])
            browser = secrets.token_urlsafe(48)
            db.execute(
                delete(MicrosoftConnectionFlow).where(MicrosoftConnectionFlow.connection_id == connection.id)
            )
            db.execute(delete(MicrosoftConnectionFlow).where(MicrosoftConnectionFlow.expires_at <= now()))
            db.add(
                MicrosoftConnectionFlow(
                    state_hash=digest,
                    organization_id=organization_id,
                    owner_id=user.id,
                    connection_id=connection.id,
                    generation=connection.generation,
                    session_hash=session_hash,
                    browser_hash=token_digest(browser),
                    encrypted_flow=vault.seal("connect:" + digest, flow),
                    expires_at=now() + FLOW_SECONDS,
                )
            )
        response = JSONResponse({"authorization_url": flow["auth_uri"]})
        response.set_cookie(
            CONNECT_COOKIE, browser, secure=True, httponly=True, samesite="none", max_age=FLOW_SECONDS
        )
        return response

    @router.post(CALLBACK)
    def callback(request: Request, params: Annotated[dict, Depends(callback_parameters)]):
        enabled()
        state, browser = params.get("state", ""), request.cookies.get(CONNECT_COOKIE, "")
        if not state or len(state) > 512 or not browser or len(browser) > 512:
            raise HTTPException(400, "invalid_connection_flow")
        digest = token_digest(state)
        with factory.begin() as db:
            # Atomic DELETE avoids reversing the membership/connection lock order.
            pending = db.scalar(
                delete(MicrosoftConnectionFlow)
                .where(
                    MicrosoftConnectionFlow.state_hash == digest,
                    MicrosoftConnectionFlow.browser_hash == token_digest(browser),
                    MicrosoftConnectionFlow.expires_at > now(),
                )
                .returning(MicrosoftConnectionFlow)
            )
            if pending is None:
                raise HTTPException(400, "invalid_connection_flow")
        # The one-use flow is committed before contacting the token endpoint.
        with factory.begin() as db:
            pending_actor(db, pending)
        try:
            grant = provider.complete_connection(
                vault.open("connect:" + digest, pending.encrypted_flow), params
            )
        except (InvalidToken, ValueError, RequestException):
            raise HTTPException(401, "microsoft_connection_failed") from None
        with factory.begin() as db:
            user, connection = pending_actor(db, pending)
            if (user.issuer, user.subject) != (grant.identity.issuer, grant.identity.subject):
                raise HTTPException(403, "microsoft_account_mismatch")
            require_allowed(db, pending.organization_id, grant.capabilities)
            connection.encrypted_cache = vault.seal(context(connection), {"cache": grant.cache})
            connection.capabilities = grant.capabilities
            connection.status, connection.connected_at = "connected", now()
            block_owner_schedules(
                db,
                pending.organization_id,
                user.id,
                "microsoft_reconnect_required",
                available=grant.capabilities,
            )
            onboarding = db.scalar(
                select(Onboarding).where(
                    Onboarding.organization_id == pending.organization_id, Onboarding.owner_id == user.id
                )
            )
            if onboarding is not None and onboarding.step == "connect_tools":
                onboarding.step = "first_result"
        response = RedirectResponse(settings.public_origin + "/", status_code=303)
        response.delete_cookie(CONNECT_COOKIE, secure=True, httponly=True, samesite="none")
        return response

    @router.delete(PREFIX, status_code=204)
    def disconnect(organization_id: str, request: Request):
        with factory.begin() as db:
            user, _ = actor(db, request, organization_id, licensed=False)
            connection = connection_for(db, user, organization_id)
            if connection is not None:
                clear_connection(connection)
                block_owner_schedules(db, organization_id, user.id, "microsoft_reconnect_required")
                db.execute(
                    delete(MicrosoftConnectionFlow).where(
                        MicrosoftConnectionFlow.connection_id == connection.id
                    )
                )
        return Response(status_code=204)

    def read(organization_id, request, capability, **arguments):
        return reader.read(
            organization_id,
            lambda db: authenticate(db, request_authorization(request, settings)),
            capability,
            **arguments,
        )

    @router.get(PREFIX + "/mail")
    def mail(organization_id: str, request: Request):
        return read(organization_id, request, "mail")

    @router.get(PREFIX + "/calendar")
    def calendar(organization_id: str, request: Request):
        return read(organization_id, request, "calendar")

    @router.post(PREFIX + "/files/search")
    def files(organization_id: str, request: Request, body: SearchInput):
        return read(organization_id, request, "files", query=body.query)

    return router
