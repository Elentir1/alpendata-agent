from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .billing_state import billing_access
from .models import Membership, Organization, User


def member(db: Session, user: User, organization_id: str, *, admin=False, licensed=True) -> Membership:
    membership = db.get(Membership, (organization_id, user.id))
    if membership is None or not membership.active:
        # The same answer for a missing organization and someone else's organization.
        raise HTTPException(404, "organization_not_found")
    if admin and membership.role != "admin":
        raise HTTPException(403, "administrator_required")
    if licensed and not membership.licensed:
        raise HTTPException(403, "license_required")
    if licensed and not billing_access(db, organization_id):
        raise HTTPException(403, "billing_access_required")
    return membership


def owned(db: Session, model, organization_id: str, user_id: str, resource_id: str):
    resource = db.scalar(
        select(model).where(
            model.id == resource_id,
            model.organization_id == organization_id,
            model.owner_id == user_id,
        )
    )
    if resource is None:
        raise HTTPException(404, "resource_not_found")
    return resource


def lock_organization(db: Session, organization_id: str) -> Organization:
    organization = db.scalar(
        select(Organization)
        .where(
            Organization.id == organization_id,
        )
        .with_for_update()
    )
    if organization is None:
        raise HTTPException(404, "organization_not_found")
    return organization
