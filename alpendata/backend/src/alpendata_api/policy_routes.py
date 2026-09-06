"""Versioned company rules serialized with in-flight personal connector actions."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field, model_validator
from sqlalchemy import select

from .access import lock_organization, member
from .auth import authenticate, request_authorization
from .models import Membership, OrganizationPolicy, now
from .organization_policy import CAPABILITIES, policy_view
from .schedule_state import block_owner_schedules
from .schemas import Input


class PolicyInput(Input):
    version: int = Field(ge=0)
    allowed_capabilities: list[Literal["mail", "calendar", "files", "files_write"]] = Field(max_length=4)

    @model_validator(mode="after")
    def document_access(self):
        if "files_write" in self.allowed_capabilities and "files" not in self.allowed_capabilities:
            raise ValueError("Saving documents also requires document access")
        return self


def policy_router(settings, factory):
    router = APIRouter()
    path = "/api/organizations/{organization_id}/policy"

    @router.get(path)
    def view(organization_id: str, request: Request):
        with factory.begin() as db:
            user = authenticate(db, request_authorization(request, settings))
            member(db, user, organization_id, licensed=False)
            return policy_view(db, organization_id)

    @router.put(path)
    def update(organization_id: str, request: Request, body: PolicyInput):
        with factory.begin() as db:
            user = authenticate(db, request_authorization(request, settings))
            lock_organization(db, organization_id)
            member(db, user, organization_id, admin=True, licensed=False)
            # All connector operations hold their owner's membership lock. Taking
            # these locks in stable order lets existing requests finish before the
            # policy commits; waiting requests then observe the new limits.
            members = db.scalars(
                select(Membership)
                .where(
                    Membership.organization_id == organization_id,
                )
                .order_by(Membership.user_id)
                .with_for_update()
            ).all()
            previous = policy_view(db, organization_id)
            if body.version != previous["version"]:
                raise HTTPException(409, "company_policy_changed")
            allowed = [item for item in CAPABILITIES if item in body.allowed_capabilities]
            if allowed == previous["allowed_capabilities"]:
                return previous
            policy = db.get(OrganizationPolicy, organization_id)
            if policy is None:
                policy = OrganizationPolicy(organization_id=organization_id)
                db.add(policy)
            policy.allowed_capabilities = allowed
            policy.version, policy.updated_by, policy.updated_at = body.version + 1, user.id, now()
            db.flush()
            for membership in members:
                block_owner_schedules(
                    db, organization_id, membership.user_id, "company_policy_denied", available=allowed
                )
            return policy_view(db, organization_id)

    return router
