from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .billing_state import billing_access
from .models import Artifact, ChatTurn, Conversation, EmailDraft, Membership, Organization, User


def visible_resource(db, resource):
    """Direct artifact/receipt URLs cannot recover a deleted private conversation."""
    item = resource
    for _ in range(5):
        if isinstance(item, Conversation):
            if item.deleted_at is not None:
                raise HTTPException(404, "resource_not_found")
            return resource
        if getattr(item, "conversation_id", None):
            item = db.get(Conversation, item.conversation_id)
        elif getattr(item, "turn_id", None) or getattr(item, "reviewed_turn_id", None):
            item = db.get(ChatTurn, getattr(item, "turn_id", None) or item.reviewed_turn_id)
        elif getattr(item, "draft_id", None):
            item = db.get(EmailDraft, item.draft_id)
        elif getattr(item, "artifact_id", None):
            item = db.get(Artifact, item.artifact_id)
        else:
            return resource
    raise HTTPException(404, "resource_not_found")


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
    return visible_resource(db, resource)


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
