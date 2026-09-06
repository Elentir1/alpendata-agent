import secrets

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .access import lock_organization, member
from .auth import token_digest
from .mail import invitation_message
from .models import Invitation, InvitationProof, Membership, Onboarding, Organization, User, now
from .schemas import MembershipInput
from .settings import Settings


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


def locked_invitation(db: Session, token: str) -> Invitation:
    invitation = db.scalar(select(Invitation).where(Invitation.token_hash == token_digest(token)))
    if invitation is None:
        raise HTTPException(404, "invitation_not_found")
    lock_organization(db, invitation.organization_id)
    # A concurrent acceptance may have committed while we waited for the organization lock.
    db.refresh(invitation)
    if invitation.revoked or invitation.consumed_at is not None or invitation.expires_at <= now():
        raise HTTPException(404, "invitation_not_found")
    inviter = db.get(Membership, (invitation.organization_id, invitation.inviter_id))
    if inviter is None or not inviter.active or inviter.role != "admin":
        raise HTTPException(404, "invitation_not_found")
    return invitation


def request_proof(db: Session, user: User, token: str, language: str, settings: Settings, mailer):
    invitation = locked_invitation(db, token)
    if db.get(Membership, (invitation.organization_id, user.id)) is not None:
        raise HTTPException(409, "already_member")
    if mailer is None:
        raise HTTPException(503, "transactional_mail_not_configured")
    recent = db.scalars(
        select(InvitationProof).where(
            InvitationProof.invitation_id == invitation.id,
            InvitationProof.created_at > now() - 3600,
        )
    ).all()
    wait_until = max((item.created_at + 60 for item in recent), default=0)
    if len(recent) >= 5:
        wait_until = max(wait_until, min(item.created_at for item in recent) + 3600)
    if wait_until > now():
        raise HTTPException(
            429, "verification_rate_limited", headers={"Retry-After": str(wait_until - now())}
        )
    proof_token = secrets.token_urlsafe(48)
    proof = InvitationProof(
        invitation_id=invitation.id,
        user_id=user.id,
        token_hash=token_digest(proof_token),
        expires_at=now() + 900,
    )
    db.add(proof)
    db.flush()
    message = invitation_message(settings, invitation.recipient_email, token, proof_token, language)
    try:
        mailer.send(message)
    except OSError:
        # The request transaction rolls back, invalidating a possibly delivered
        # proof. The caller must explicitly retry; we never duplicate SMTP DATA.
        raise HTTPException(502, "verification_delivery_failed") from None
    local, domain = invitation.recipient_email.rsplit("@", 1)
    return {
        "status": "verification_sent",
        "expires_at": proof.expires_at,
        "recipient_hint": local[:1] + "***@" + domain,
    }


def accept(db: Session, user: User, token: str, verification_token: str | None = None) -> str:
    invitation = locked_invitation(db, token)
    # A remembered email or a Microsoft claim is never sufficient. The proof
    # must be fresh and bound to BOTH this invitation and the authenticated user.
    proof = db.scalar(
        select(InvitationProof).where(
            InvitationProof.invitation_id == invitation.id,
            InvitationProof.user_id == user.id,
            InvitationProof.token_hash == token_digest(verification_token or ""),
            InvitationProof.consumed_at.is_(None),
            InvitationProof.expires_at > now(),
        )
    )
    if proof is None:
        raise HTTPException(403, "invitation_email_verification_required")
    if db.get(Membership, (invitation.organization_id, user.id)) is not None:
        raise HTTPException(409, "already_member")
    proof.consumed_at = now()
    user.verified_email = invitation.recipient_email
    invitation.consumed_at = now()
    add_member(db, invitation.organization_id, user.id, "member")
    return invitation.organization_id


def update_membership(db: Session, actor: User, organization_id: str, user_id: str, body: MembershipInput):
    organization = lock_organization(db, organization_id)
    member(db, actor, organization_id, admin=True, licensed=False)
    target = db.get(Membership, (organization_id, user_id))
    if target is None:
        raise HTTPException(404, "member_not_found")
    if target.version != body.version:
        raise HTTPException(409, "member_state_changed")
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
    target.version += 1
    db.flush()
    if not body.active or not body.licensed:
        from .schedule_state import block_owner_schedules

        block_owner_schedules(db, organization_id, user_id, "agent_access_revoked")
    return target
