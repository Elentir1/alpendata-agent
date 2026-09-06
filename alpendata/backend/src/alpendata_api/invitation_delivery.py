"""Initial invitations: commit the reservation before SMTP, never replay an uncertain send."""

from email.message import EmailMessage
from email.utils import formatdate
from typing import Literal
from urllib.parse import urlencode
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import func, select

from . import organizations
from .access import lock_organization, member
from .auth import authenticate, request_authorization
from .models import Invitation, now
from .schemas import InviteInput


class InvitationEmail(InviteInput):
    request_id: UUID
    language: Literal["fr", "en"]


def delivery_view(item):
    status = item.delivery_status
    if status == "sending" and item.delivery_started_at <= now() - 120:
        status = "unknown"
    return {
        "id": item.id,
        "email": item.recipient_email,
        "expires_at": item.expires_at,
        "delivery_status": status,
        "revoked": item.revoked,
        "accepted": item.consumed_at is not None,
    }


def initial_message(settings, invitation, token, company):
    message = EmailMessage()
    message["From"] = InviteInput(email=settings.smtp_sender).email
    message["To"] = invitation.recipient_email
    message["Date"] = formatdate(localtime=False)
    message["Message-ID"] = f"<invitation-{invitation.id}@{message['From'].rsplit('@', 1)[1]}>"
    link = settings.public_origin + "/join#" + urlencode({"invitation": token})
    texts = {
        "fr": (
            "Votre invitation AlpenData",
            "{company} vous invite sur AlpenData.\n\n{link}\n\n"
            "Connectez-vous avec votre compte, puis vérifiez votre adresse pour rejoindre votre entreprise. "
            "Vous configurerez votre propre assistant et vos connexions personnelles.\n\nAlpenData",
        ),
        "en": (
            "Your AlpenData invitation",
            "{company} invites you to AlpenData.\n\n{link}\n\n"
            "Sign in with your account, then verify your email address to join your company. "
            "You will set up your own assistant and personal connections.\n\nAlpenData",
        ),
    }
    title, body = texts[invitation.delivery_language]
    message["Subject"] = title
    message.set_content(body.format(company=company, link=link))
    return message


def invitation_delivery_router(settings, factory, mailer):
    router = APIRouter()

    @router.post("/api/organizations/{organization_id}/invitations/email", status_code=201)
    def send(organization_id: str, body: InvitationEmail, request: Request):
        with factory.begin() as db:
            actor = authenticate(db, request_authorization(request, settings))
            company = lock_organization(db, organization_id)
            member(db, actor, organization_id, admin=True, licensed=False)
            previous = db.scalar(
                select(Invitation).where(
                    Invitation.organization_id == organization_id,
                    Invitation.delivery_request_id == str(body.request_id),
                )
            )
            if previous:
                if (previous.recipient_email, previous.delivery_language) != (body.email, body.language):
                    raise HTTPException(409, "invitation_request_conflict")
                return delivery_view(previous)
            if mailer is None or not settings.smtp_enabled:
                raise HTTPException(503, "transactional_mail_not_configured")
            recent = db.scalar(
                select(func.count())
                .select_from(Invitation)
                .where(
                    Invitation.organization_id == organization_id,
                    Invitation.delivery_started_at > now() - 3600,
                )
            )
            if recent >= 20:
                raise HTTPException(429, "invitation_rate_limited", headers={"Retry-After": "3600"})
            invitation, token = organizations.invite(
                db, actor, organization_id, body.email, settings.invitation_lifetime_seconds
            )
            invitation.delivery_request_id = str(body.request_id)
            invitation.delivery_language = body.language
            invitation.delivery_started_at = now()
            invitation.delivery_status = "sending"
            message = initial_message(settings, invitation, token, company.name)
            identifier = invitation.id
        # Only this request owns the raw token. Neither crash recovery nor a browser retry can send it again.
        status = "submitted"
        try:
            mailer.send(message)
        except Exception:
            status = "unknown"
        with factory.begin() as db:
            item = db.get(Invitation, identifier)
            item.delivery_status = status
            return delivery_view(item)

    return router
