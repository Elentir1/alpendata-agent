"""Personal connection consent and encrypted Infomaniak mailbox access."""

from typing import Literal

from cryptography.fernet import InvalidToken
from fastapi import APIRouter, HTTPException, Request
from pydantic import EmailStr, Field, SecretStr, model_validator
from sqlalchemy import select

from .auth import authenticate, request_authorization
from .connections import lock_member
from .infomaniak_dav import InfomaniakDav, drive_origin, safe_url
from .infomaniak_mail import InfomaniakMail
from .models import InfomaniakConnection, Onboarding
from .organization_policy import allowed_capabilities, require_allowed
from .schemas import Input
from .vault import Vault


class ConnectionInput(Input):
    email: EmailStr
    password: SecretStr = Field(min_length=1, max_length=1024)
    capabilities: list[Literal["mail", "mail_send"]] = Field(default_factory=lambda: ["mail"], min_length=1)


class DavInput(Input):
    service: Literal["calendar", "files"]
    username: str = Field(min_length=1, max_length=256, pattern=r"^[^\r\n\x00]+$")
    password: SecretStr = Field(min_length=1, max_length=1024)
    calendar_url: str = Field(default="https://sync.infomaniak.com/", max_length=2048)
    drive_id: str = Field(default="", max_length=16)
    allow_write: bool = False

    @model_validator(mode="after")
    def validate_service(self):
        if self.service == "calendar":
            safe_url("https://sync.infomaniak.com", self.calendar_url)
        else:
            drive_origin(self.drive_id)
        return self


class SearchInput(Input):
    query: str = Field(default="", max_length=256, pattern=r"^[^\r\n\x00]*$")


def connection(db, organization_id, owner_id):
    return db.scalar(
        select(InfomaniakConnection)
        .where(
            InfomaniakConnection.organization_id == organization_id, InfomaniakConnection.owner_id == owner_id
        )
        .execution_options(populate_existing=True)
    )


def context(organization_id, owner_id):
    return f"infomaniak:{organization_id}:{owner_id}"


class InfomaniakReader:
    def __init__(self, settings, factory, transport=None, dav=None):
        self.settings, self.factory = settings, factory
        self.transport = transport or InfomaniakMail()
        self.dav = dav or InfomaniakDav()

    def execute(self, organization_id, authorize, capability, perform):
        if not self.settings.credential_keys:
            raise HTTPException(503, "infomaniak_not_configured")
        with self.factory.begin() as db:
            user = authorize(db)
            lock_member(db, user, organization_id)
            require_allowed(db, organization_id, [capability])
            item = connection(db, organization_id, user.id)
            if not item or item.status != "connected" or capability not in item.capabilities:
                raise HTTPException(403, "infomaniak_permission_required")
            try:
                credentials = Vault(self.settings.credential_keys).open(
                    context(organization_id, user.id), item.encrypted_credentials
                )
            except InvalidToken:
                raise HTTPException(409, "infomaniak_reconnect_required") from None
            return perform(self.transport, credentials)

    def read(self, organization_id, authorize, capability, *, operation="read", **arguments):
        if capability in ("calendar", "files"):

            def perform(_transport, credentials):
                service = credentials.get(capability)
                if not service:
                    raise HTTPException(409, "infomaniak_reconnect_required")
                if capability == "calendar" and not arguments and operation == "read":
                    return self.dav.calendar(service)
                if capability == "files" and operation == "download":
                    return self.dav.download(service, **arguments)
                if capability == "files" and operation == "read":
                    return self.dav.files(service, SearchInput.model_validate(arguments).query)
                raise HTTPException(400, "agent_tool_arguments_invalid")

            return self.execute(organization_id, authorize, capability, perform)
        if capability != "mail" or operation != "read":
            raise HTTPException(403, "infomaniak_permission_required")
        body = SearchInput.model_validate(arguments)
        return self.execute(
            organization_id,
            authorize,
            "mail",
            lambda transport, credentials: transport.read(credentials, body.query),
        )

    def send(self, organization_id, authorize, message, files, correlation_id):
        return self.execute(
            organization_id,
            authorize,
            "mail_send",
            lambda transport, credentials: transport.send(credentials, message, files, correlation_id),
        )


def infomaniak_router(settings, factory, transport=None):
    router = APIRouter()
    path = "/api/organizations/{organization_id}/integrations/infomaniak"
    reader = InfomaniakReader(settings, factory, transport)

    def actor(db, request, organization_id, write=False):
        user = authenticate(db, request_authorization(request, settings))
        lock_member(db, user, organization_id, licensed=write)
        return user

    @router.get(path)
    def status(organization_id: str, request: Request):
        with factory.begin() as db:
            user = actor(db, request, organization_id)
            item = connection(db, organization_id, user.id)
            return {
                "available": bool(settings.credential_keys),
                "status": item.status if item else "disconnected",
                "email": item.email if item and item.status == "connected" else None,
                "capabilities": item.capabilities if item and item.status == "connected" else [],
                "allowed_capabilities": allowed_capabilities(db, organization_id),
            }

    @router.put(path)
    def connect(organization_id: str, request: Request, body: ConnectionInput):
        if not settings.credential_keys:
            raise HTTPException(503, "infomaniak_not_configured")
        with factory.begin() as db:
            user = actor(db, request, organization_id, write=True)
            require_allowed(db, organization_id, body.capabilities)
            credentials = {"email": str(body.email), "password": body.password.get_secret_value()}
            reader.transport.verify(credentials)
            item = connection(db, organization_id, user.id)
            if not item:
                item = InfomaniakConnection(
                    organization_id=organization_id, owner_id=user.id, email=str(body.email)
                )
                db.add(item)
            if item.encrypted_credentials:
                previous = Vault(settings.credential_keys).open(
                    context(organization_id, user.id), item.encrypted_credentials
                )
                credentials.update({key: previous[key] for key in ("calendar", "files") if key in previous})
            existing = [
                key
                for key in (item.capabilities or [])
                if key in ("calendar", "calendar_write", "files", "files_write")
            ]
            item.email, item.status, item.capabilities = (
                str(body.email),
                "connected",
                sorted(set(body.capabilities + existing)),
            )
            item.encrypted_credentials = Vault(settings.credential_keys).seal(
                context(organization_id, user.id), credentials
            )
            onboarding = db.scalar(
                select(Onboarding).where(
                    Onboarding.organization_id == organization_id, Onboarding.owner_id == user.id
                )
            )
            if onboarding is not None and onboarding.step == "connect_tools":
                onboarding.step = "first_result"
            return {"status": "connected", "email": item.email, "capabilities": item.capabilities}

    @router.put(path + "/dav")
    def connect_dav(organization_id: str, request: Request, body: DavInput):
        if not settings.credential_keys:
            raise HTTPException(503, "infomaniak_not_configured")
        with factory.begin() as db:
            user = actor(db, request, organization_id, write=True)
            require_allowed(db, organization_id, [body.service])
            if body.allow_write:
                require_allowed(db, organization_id, [body.service + "_write"])
            service = {"username": body.username, "password": body.password.get_secret_value()}
            if body.service == "calendar":
                service["url"] = body.calendar_url
                reader.dav.calendars(service)
            else:
                service["drive_id"] = body.drive_id
                reader.dav.properties(service, drive_origin(body.drive_id), "/")
            item = connection(db, organization_id, user.id)
            credentials = {}
            if item and item.encrypted_credentials:
                credentials = Vault(settings.credential_keys).open(
                    context(organization_id, user.id), item.encrypted_credentials
                )
            if not item:
                item = InfomaniakConnection(
                    organization_id=organization_id, owner_id=user.id, email=body.username
                )
                db.add(item)
            credentials[body.service] = service
            capabilities = set(item.capabilities or []) - {body.service + "_write"}
            capabilities.add(body.service)
            if body.allow_write:
                capabilities.add(body.service + "_write")
            item.capabilities = sorted(capabilities)
            item.status = "connected"
            item.encrypted_credentials = Vault(settings.credential_keys).seal(
                context(organization_id, user.id), credentials
            )
            onboarding = db.scalar(
                select(Onboarding).where(
                    Onboarding.organization_id == organization_id, Onboarding.owner_id == user.id
                )
            )
            if onboarding is not None and onboarding.step == "connect_tools":
                onboarding.step = "first_result"
            return {"status": "connected", "capabilities": item.capabilities}

    @router.delete(path, status_code=204)
    def disconnect(organization_id: str, request: Request):
        with factory.begin() as db:
            user = actor(db, request, organization_id)
            item = connection(db, organization_id, user.id)
            if item:
                item.status, item.capabilities, item.encrypted_credentials = "disconnected", [], None

    @router.post(path + "/mail/search")
    def search(organization_id: str, request: Request, body: SearchInput):
        return reader.read(
            organization_id,
            lambda db: actor(db, request, organization_id, write=True),
            "mail",
            query=body.query,
        )

    return router
