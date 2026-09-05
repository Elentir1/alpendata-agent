from collections.abc import Generator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import organizations
from .access import lock_organization, member, owned
from .auth import SESSION_COOKIE, authenticate, request_authorization, token_digest
from .database import database_factory
from .mail import SMTPMailer
from .models import AuthSession, Invitation, Membership, Onboarding, Organization, PersonalResource, User
from .schemas import (
    AcceptInvitation,
    InviteInput,
    MembershipInput,
    OnboardingInput,
    OrganizationInput,
    ResourceInput,
    VerifyInvitation,
)
from .settings import Settings
from .signin import signin_router


def create_app(settings: Settings, *, signin_provider=None, mailer=None) -> FastAPI:
    engine, factory = database_factory(settings.database_url)
    if mailer is None and settings.smtp_enabled:
        mailer = SMTPMailer(settings)

    @asynccontextmanager
    async def lifespan(_app):
        yield
        engine.dispose()

    app = FastAPI(title="AlpenData API", version="0.1.0", lifespan=lifespan)
    app.state.engine, app.state.session_factory = engine, factory
    app.include_router(signin_router(settings, factory, signin_provider))

    @app.middleware("http")
    async def private_responses(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    def database() -> Generator[Session, None, None]:
        with factory.begin() as session:
            yield session

    DB = Annotated[Session, Depends(database)]

    def current_user(db: DB, request: Request) -> User:
        return authenticate(db, request_authorization(request, settings))

    Actor = Annotated[User, Depends(current_user)]

    @app.get("/health/live")
    def live():
        return {"status": "ok"}

    @app.get("/api/me")
    def me(actor: Actor, db: DB):
        memberships = db.scalars(
            select(Membership).where(
                Membership.user_id == actor.id,
                Membership.active.is_(True),
            )
        ).all()
        return {
            "id": actor.id,
            "display_name": actor.display_name,
            "memberships": [membership_view(item) for item in memberships],
        }

    @app.post("/api/logout", status_code=204)
    def logout(actor: Actor, db: DB, request: Request):
        authorization = request_authorization(request, settings)
        session = db.get(AuthSession, token_digest(authorization.removeprefix("Bearer ")))
        session.revoked = True
        response = Response(status_code=204)
        response.delete_cookie(SESSION_COOKIE, secure=True, httponly=True, samesite="lax")
        return response

    @app.post("/api/organizations", status_code=201)
    def create_organization(body: OrganizationInput, actor: Actor, db: DB):
        organization = organizations.create_organization(db, actor, body.name, settings.pilot_seats)
        return {"id": organization.id, "name": organization.name, "seat_capacity": organization.seat_capacity}

    @app.get("/api/organizations/{organization_id}")
    def get_organization(organization_id: str, actor: Actor, db: DB):
        member(db, actor, organization_id, licensed=False)
        organization = db.get(Organization, organization_id)
        return {"id": organization.id, "name": organization.name}

    @app.get("/api/organizations/{organization_id}/members")
    def list_members(organization_id: str, actor: Actor, db: DB):
        member(db, actor, organization_id, admin=True, licensed=False)
        return {
            "members": [
                membership_view(item)
                for item in db.scalars(
                    select(Membership).where(Membership.organization_id == organization_id)
                )
            ]
        }

    @app.patch("/api/organizations/{organization_id}/members/{user_id}")
    def update_member(organization_id: str, user_id: str, body: MembershipInput, actor: Actor, db: DB):
        return membership_view(organizations.update_membership(db, actor, organization_id, user_id, body))

    @app.post("/api/organizations/{organization_id}/invitations", status_code=201)
    def create_invitation(organization_id: str, body: InviteInput, actor: Actor, db: DB):
        invitation, token = organizations.invite(
            db,
            actor,
            organization_id,
            body.email,
            settings.invitation_lifetime_seconds,
        )
        # Returned once for manual sharing until a transactional mail service is connected.
        return {"id": invitation.id, "token": token, "expires_at": invitation.expires_at}

    @app.delete("/api/organizations/{organization_id}/invitations/{invitation_id}", status_code=204)
    def revoke_invitation(organization_id: str, invitation_id: str, actor: Actor, db: DB):
        lock_organization(db, organization_id)
        member(db, actor, organization_id, admin=True, licensed=False)
        invitation = db.scalar(
            select(Invitation).where(
                Invitation.id == invitation_id,
                Invitation.organization_id == organization_id,
            )
        )
        if invitation is None:
            raise HTTPException(404, "invitation_not_found")
        invitation.revoked = True
        return Response(status_code=204)

    @app.post("/api/invitations/accept")
    def accept_invitation(body: AcceptInvitation, actor: Actor, db: DB):
        return {"organization_id": organizations.accept(db, actor, body.token, body.verification_token)}

    @app.post("/api/invitations/verify", status_code=202)
    def verify_invitation(body: VerifyInvitation, actor: Actor, db: DB):
        return organizations.request_proof(db, actor, body.token, body.language, settings, mailer)

    @app.get("/api/organizations/{organization_id}/onboarding")
    def get_onboarding(organization_id: str, actor: Actor, db: DB):
        member(db, actor, organization_id)
        return onboarding_view(personal_onboarding(db, organization_id, actor.id))

    @app.put("/api/organizations/{organization_id}/onboarding")
    def save_onboarding(organization_id: str, body: OnboardingInput, actor: Actor, db: DB):
        member(db, actor, organization_id)
        onboarding = personal_onboarding(db, organization_id, actor.id)
        onboarding.language = body.language
        onboarding.answers = body.model_dump(exclude={"language"})
        # Completion requires a connected tool and a first useful result in the next product slice.
        onboarding.step = "connect_tools"
        return onboarding_view(onboarding)

    @app.post("/api/organizations/{organization_id}/personal-resources", status_code=201)
    def create_resource(organization_id: str, body: ResourceInput, actor: Actor, db: DB):
        member(db, actor, organization_id)
        resource = PersonalResource(organization_id=organization_id, owner_id=actor.id, **body.model_dump())
        db.add(resource)
        db.flush()
        return resource_view(resource)

    @app.get("/api/organizations/{organization_id}/personal-resources")
    def list_resources(organization_id: str, actor: Actor, db: DB):
        member(db, actor, organization_id)
        return {
            "resources": [
                resource_view(item)
                for item in db.scalars(
                    select(PersonalResource)
                    .where(
                        PersonalResource.organization_id == organization_id,
                        PersonalResource.owner_id == actor.id,
                    )
                    .order_by(PersonalResource.created_at, PersonalResource.id)
                )
            ]
        }

    @app.get("/api/organizations/{organization_id}/personal-resources/{resource_id}")
    def get_resource(organization_id: str, resource_id: str, actor: Actor, db: DB):
        member(db, actor, organization_id)
        return resource_view(owned(db, PersonalResource, organization_id, actor.id, resource_id))

    @app.delete("/api/organizations/{organization_id}/personal-resources/{resource_id}", status_code=204)
    def delete_resource(organization_id: str, resource_id: str, actor: Actor, db: DB):
        member(db, actor, organization_id)
        db.delete(owned(db, PersonalResource, organization_id, actor.id, resource_id))
        return Response(status_code=204)

    return app


def personal_onboarding(db: Session, organization_id: str, user_id: str) -> Onboarding:
    onboarding = db.scalar(
        select(Onboarding).where(
            Onboarding.organization_id == organization_id,
            Onboarding.owner_id == user_id,
        )
    )
    if onboarding is None:
        raise HTTPException(404, "onboarding_not_found")
    return onboarding


def onboarding_view(item: Onboarding):
    return {"language": item.language, "step": item.step, "answers": item.answers}


def membership_view(item: Membership):
    return {
        "organization_id": item.organization_id,
        "user_id": item.user_id,
        "role": item.role,
        "active": item.active,
        "licensed": item.licensed,
    }


def resource_view(item: PersonalResource):
    return {
        "id": item.id,
        "kind": item.kind,
        "title": item.title,
        "content": item.content,
        "created_at": item.created_at,
    }


def from_environment() -> FastAPI:
    return create_app(Settings.from_environment())
