import secrets

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .access import lock_organization, member
from .auth import token_digest
from .models import Invitation, Membership, Onboarding, Organization, User, now
from .schemas import MembershipInput


def add_member(db: Session, organization_id: str, user_id: str, role: str):
    db.add(Membership(organization_id=organization_id, user_id=user_id, role=role))
    db.flush()
    db.add(Onboarding(organization_id=organization_id, owner_id=user_id))
    db.flush()


def create_organization(db: Session, user: User, name: str, seats: int) -> Organization:
    organization = Organization(name=name, seat_capacity=seats)
    db.add(organization)
    db.flush()
    add_member(db, organization.id, user.id, "admin")
    return organization


def active_invites(organization_id: str):
    return (
        Invitation.organization_id == organization_id,
        Invitation.consumed_at.is_(None),
        Invitation.revoked.is_(False),
        Invitation.expires_at > now(),
    )


def occupied_seats(db: Session, organization_id: str) -> int:
    members = db.scalar(
        select(func.count())
        .select_from(Membership)
        .where(
            Membership.organization_id == organization_id,
            Membership.active.is_(True),
            Membership.licensed.is_(True),
        )
    )
    pending = db.scalar(select(func.count()).select_from(Invitation).where(*active_invites(organization_id)))
    return members + pending


def invite(db: Session, user: User, organization_id: str, email: str, lifetime: int):
    organization = lock_organization(db, organization_id)
    member(db, user, organization_id, admin=True, licensed=False)
    existing = db.scalar(
        select(Membership)
        .join(User)
        .where(
            Membership.organization_id == organization_id,
            User.verified_email == email,
        )
    )
    pending = db.scalar(
        select(Invitation).where(
            *active_invites(organization_id),
            Invitation.recipient_email == email,
        )
    )
    if existing is not None or pending is not None:
        raise HTTPException(409, "already_member_or_invited")
    if occupied_seats(db, organization_id) >= organization.seat_capacity:
        raise HTTPException(409, "no_available_license")
    token = secrets.token_urlsafe(48)
    invitation = Invitation(
        organization_id=organization_id,
        recipient_email=email,
        token_hash=token_digest(token),
        expires_at=now() + lifetime,
        inviter_id=user.id,
    )
    db.add(invitation)
    db.flush()
    return invitation, token


def accept(db: Session, user: User, token: str) -> str:
    invitation = db.scalar(select(Invitation).where(Invitation.token_hash == token_digest(token)))
    if invitation is None:
        raise HTTPException(404, "invitation_not_found")
    lock_organization(db, invitation.organization_id)
    # A concurrent acceptance may have committed while we waited for the organization lock.
    db.refresh(invitation)
    if invitation.revoked or invitation.consumed_at is not None or invitation.expires_at <= now():
        raise HTTPException(404, "invitation_not_found")
    if not user.verified_email or user.verified_email.casefold() != invitation.recipient_email:
        raise HTTPException(403, "invitation_recipient_mismatch")
    inviter = db.get(Membership, (invitation.organization_id, invitation.inviter_id))
    if inviter is None or not inviter.active or inviter.role != "admin":
        raise HTTPException(404, "invitation_not_found")
    if db.get(Membership, (invitation.organization_id, user.id)) is not None:
        raise HTTPException(409, "already_member")
    invitation.consumed_at = now()
    add_member(db, invitation.organization_id, user.id, "member")
    return invitation.organization_id


def update_membership(db: Session, actor: User, organization_id: str, user_id: str, body: MembershipInput):
    organization = lock_organization(db, organization_id)
    member(db, actor, organization_id, admin=True, licensed=False)
    target = db.get(Membership, (organization_id, user_id))
    if target is None:
        raise HTTPException(404, "member_not_found")
    if target.active and target.role == "admin" and (not body.active or body.role != "admin"):
        admins = db.scalar(
            select(func.count())
            .select_from(Membership)
            .where(
                Membership.organization_id == organization_id,
                Membership.active.is_(True),
                Membership.role == "admin",
            )
        )
        if admins == 1:
            raise HTTPException(409, "last_administrator")
    if body.active and body.licensed and not (target.active and target.licensed):
        if occupied_seats(db, organization_id) >= organization.seat_capacity:
            raise HTTPException(409, "no_available_license")
    target.role, target.active, target.licensed = body.role, body.active, body.licensed
    db.flush()
    return target
