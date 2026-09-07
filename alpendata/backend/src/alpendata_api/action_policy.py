"""Personal autonomy never supplies a connection or overrides company limits."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field
from sqlalchemy import select

from .auth import authenticate, request_authorization
from .connections import lock_member
from .models import InfomaniakConnection, MicrosoftConnection, PersonalActionPolicy, now
from .organization_policy import allowed_capabilities, require_allowed
from .schemas import Input


def personal_policy(db, organization_id, owner_id):
    return db.scalar(
        select(PersonalActionPolicy)
        .where(
            PersonalActionPolicy.organization_id == organization_id,
            PersonalActionPolicy.owner_id == owner_id,
        )
        .execution_options(populate_existing=True)
    )


def require_email_autonomy(db, organization_id, owner_id, version=None):
    require_allowed(db, organization_id, ["mail_send", "mail_autonomous"])
    policy = personal_policy(db, organization_id, owner_id)
    if policy is None or policy.email_mode != "automatic":
        raise HTTPException(403, "email_confirmation_required")
    if version is not None and policy.version != version:
        raise HTTPException(409, "personal_policy_changed")
    return policy.version


def email_autonomy_available(db, organization_id, owner_id, provider=None):
    try:
        require_email_autonomy(db, organization_id, owner_id)
    except HTTPException:
        return False
    connection = db.scalar(
        select(MicrosoftConnection).where(
            MicrosoftConnection.organization_id == organization_id,
            MicrosoftConnection.owner_id == owner_id,
        )
    )
    if (
        provider != "infomaniak"
        and connection
        and connection.status == "connected"
        and "mail_send" in connection.capabilities
    ):
        return True
    alternative = db.scalar(
        select(InfomaniakConnection).where(
            InfomaniakConnection.organization_id == organization_id, InfomaniakConnection.owner_id == owner_id
        )
    )
    return bool(
        provider != "microsoft"
        and alternative
        and alternative.status == "connected"
        and "mail_send" in alternative.capabilities
    )


def policy_view(db, organization_id, owner_id):
    policy = personal_policy(db, organization_id, owner_id)
    allowed = allowed_capabilities(db, organization_id)
    return {
        "version": policy.version if policy else 0,
        "email_mode": policy.email_mode if policy else "confirm",
        "automatic_allowed": {"mail_send", "mail_autonomous"} <= set(allowed),
        "automatic_available": email_autonomy_available(db, organization_id, owner_id),
        "updated_at": policy.updated_at if policy else None,
    }


class PolicyInput(Input):
    version: int = Field(ge=0)
    email_mode: Literal["confirm", "automatic"]
    acknowledged: bool = False


def action_policy_router(settings, factory):
    router = APIRouter()
    path = "/api/organizations/{organization_id}/action-policy"

    def actor(db, request, organization_id):
        user = authenticate(db, request_authorization(request, settings))
        # A user who lost a seat can still reduce their authority.
        lock_member(db, user, organization_id, licensed=False)
        return user

    @router.get(path)
    def read(organization_id: str, request: Request):
        with factory.begin() as db:
            user = actor(db, request, organization_id)
            return policy_view(db, organization_id, user.id)

    @router.put(path)
    def update(organization_id: str, request: Request, body: PolicyInput):
        with factory.begin() as db:
            user = actor(db, request, organization_id)
            policy = personal_policy(db, organization_id, user.id)
            if body.version != (policy.version if policy else 0):
                raise HTTPException(409, "personal_policy_changed")
            if body.email_mode == "automatic":
                lock_member(db, user, organization_id)
                require_allowed(db, organization_id, ["mail_send", "mail_autonomous"])
                if not body.acknowledged:
                    raise HTTPException(409, "email_autonomy_acknowledgement_required")
            if policy is None:
                policy = PersonalActionPolicy(organization_id=organization_id, owner_id=user.id)
                db.add(policy)
            policy.email_mode, policy.version, policy.updated_at = body.email_mode, body.version + 1, now()
            db.flush()
            if body.email_mode == "confirm":
                from .schedule_state import block_owner_schedules

                block_owner_schedules(
                    db, organization_id, user.id, "email_confirmation_required", autonomous_only=True
                )
            return policy_view(db, organization_id, user.id)

    return router
