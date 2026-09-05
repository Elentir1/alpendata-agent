"""Ownership is represented in keys as well as in request authorization."""

import time
import uuid

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def new_id() -> str:
    return str(uuid.uuid4())


def now() -> int:
    return int(time.time())


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "alpendata_users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    issuer: Mapped[str] = mapped_column(String(512))
    subject: Mapped[str] = mapped_column(String(255))
    verified_email: Mapped[str | None] = mapped_column(String(320))
    display_name: Mapped[str] = mapped_column(String(160))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("issuer", "subject"),)


class AuthSession(Base):
    __tablename__ = "alpendata_auth_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("alpendata_users.id"), index=True)
    expires_at: Mapped[int] = mapped_column(Integer)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class SignInFlow(Base):
    __tablename__ = "alpendata_signin_flows"
    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    browser_hash: Mapped[str] = mapped_column(String(64))
    encrypted_flow: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[int] = mapped_column(Integer, index=True)


class Organization(Base):
    __tablename__ = "alpendata_organizations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160))
    seat_capacity: Mapped[int] = mapped_column(Integer)
    __table_args__ = (CheckConstraint("seat_capacity > 0", name="ck_organization_seats"),)


class Membership(Base):
    __tablename__ = "alpendata_memberships"
    organization_id: Mapped[str] = mapped_column(ForeignKey("alpendata_organizations.id"), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("alpendata_users.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(16))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    licensed: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (CheckConstraint("role IN ('admin', 'member')", name="ck_membership_role"),)


class Invitation(Base):
    __tablename__ = "alpendata_invitations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("alpendata_organizations.id"), index=True)
    recipient_email: Mapped[str] = mapped_column(String(320))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[int] = mapped_column(Integer)
    consumed_at: Mapped[int | None] = mapped_column(Integer)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    inviter_id: Mapped[str] = mapped_column(String(36))
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "inviter_id"],
            ["alpendata_memberships.organization_id", "alpendata_memberships.user_id"],
        ),
    )


class OwnedMixin:
    organization_id: Mapped[str] = mapped_column(String(36), index=True)
    owner_id: Mapped[str] = mapped_column(String(36), index=True)


class InvitationProof(Base):
    __tablename__ = "alpendata_invitation_proofs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    invitation_id: Mapped[str] = mapped_column(ForeignKey("alpendata_invitations.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("alpendata_users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[int] = mapped_column(Integer, default=now)
    expires_at: Mapped[int] = mapped_column(Integer)
    consumed_at: Mapped[int | None] = mapped_column(Integer)


def ownership_constraint():
    return ForeignKeyConstraint(
        ["organization_id", "owner_id"],
        ["alpendata_memberships.organization_id", "alpendata_memberships.user_id"],
    )


class Onboarding(OwnedMixin, Base):
    __tablename__ = "alpendata_onboardings"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    language: Mapped[str] = mapped_column(String(2), default="fr")
    step: Mapped[str] = mapped_column(String(24), default="introduction")
    answers: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (
        ownership_constraint(),
        UniqueConstraint("organization_id", "owner_id"),
        CheckConstraint("language IN ('fr', 'en')", name="ck_onboarding_language"),
    )


class PersonalResource(OwnedMixin, Base):
    __tablename__ = "alpendata_personal_resources"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(24))
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[int] = mapped_column(Integer, default=now)
    __table_args__ = (
        ownership_constraint(),
        CheckConstraint("kind IN ('memory', 'conversation')", name="ck_personal_resource_kind"),
    )


class MicrosoftConnection(OwnedMixin, Base):
    __tablename__ = "alpendata_microsoft_connections"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    generation: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(24), default="disconnected")
    capabilities: Mapped[list] = mapped_column(JSON, default=list)
    encrypted_cache: Mapped[str | None] = mapped_column(Text)
    connected_at: Mapped[int | None] = mapped_column(Integer)
    __table_args__ = (
        ownership_constraint(),
        UniqueConstraint("organization_id", "owner_id"),
        CheckConstraint(
            "status IN ('disconnected', 'connected', 'reconnect_required')", name="ck_microsoft_status"
        ),
    )


class MicrosoftConnectionFlow(OwnedMixin, Base):
    __tablename__ = "alpendata_microsoft_connection_flows"
    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    connection_id: Mapped[str] = mapped_column(ForeignKey("alpendata_microsoft_connections.id"))
    generation: Mapped[int] = mapped_column(Integer)
    session_hash: Mapped[str] = mapped_column(ForeignKey("alpendata_auth_sessions.token_hash"))
    browser_hash: Mapped[str] = mapped_column(String(64))
    encrypted_flow: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[int] = mapped_column(Integer, index=True)
    __table_args__ = (ownership_constraint(),)


class Conversation(OwnedMixin, Base):
    __tablename__ = "alpendata_conversations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(160))
    purpose: Mapped[str] = mapped_column(String(24), default="chat", server_default="chat")
    language: Mapped[str] = mapped_column(String(2))
    provider: Mapped[str] = mapped_column(String(24))
    model: Mapped[str] = mapped_column(String(200))
    system_prompt: Mapped[str] = mapped_column(Text)
    capabilities: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[int] = mapped_column(Integer, default=now)
    __table_args__ = (
        ownership_constraint(),
        UniqueConstraint("id", "organization_id", "owner_id"),
        CheckConstraint("language IN ('fr', 'en')", name="ck_conversation_language"),
    )


class ChatTurn(OwnedMixin, Base):
    __tablename__ = "alpendata_chat_turns"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(String(36), index=True)
    request_id: Mapped[str] = mapped_column(String(36))
    sequence: Mapped[int] = mapped_column(Integer)
    message: Mapped[str] = mapped_column(Text)
    response: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    error_code: Mapped[str | None] = mapped_column(String(80))
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    lease_id: Mapped[str | None] = mapped_column(String(36))
    lease_expires_at: Mapped[int | None] = mapped_column(Integer, index=True)
    created_at: Mapped[int] = mapped_column(Integer, default=now)
    started_at: Mapped[int | None] = mapped_column(Integer)
    finished_at: Mapped[int | None] = mapped_column(Integer)
    __table_args__ = (
        ForeignKeyConstraint(
            ["conversation_id", "organization_id", "owner_id"],
            [
                "alpendata_conversations.id",
                "alpendata_conversations.organization_id",
                "alpendata_conversations.owner_id",
            ],
        ),
        UniqueConstraint("id", "organization_id", "owner_id"),
        UniqueConstraint("organization_id", "owner_id", "request_id"),
        UniqueConstraint("conversation_id", "sequence"),
        CheckConstraint("sequence > 0", name="ck_chat_turn_sequence"),
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'cancelled', 'interrupted')",
            name="ck_chat_turn_status",
        ),
    )


class ModelCall(OwnedMixin, Base):
    __tablename__ = "alpendata_model_calls"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    turn_id: Mapped[str] = mapped_column(String(36), index=True)
    provider: Mapped[str] = mapped_column(String(24))
    model: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(24), default="started")
    prompt_tokens: Mapped[int | None] = mapped_column(BigInteger)
    completion_tokens: Mapped[int | None] = mapped_column(BigInteger)
    total_tokens: Mapped[int | None] = mapped_column(BigInteger)
    error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[int] = mapped_column(Integer, default=now)
    finished_at: Mapped[int | None] = mapped_column(Integer)
    __table_args__ = (
        ForeignKeyConstraint(
            ["turn_id", "organization_id", "owner_id"],
            [
                "alpendata_chat_turns.id",
                "alpendata_chat_turns.organization_id",
                "alpendata_chat_turns.owner_id",
            ],
        ),
        CheckConstraint("status IN ('started', 'completed', 'failed')", name="ck_model_call_status"),
        CheckConstraint(
            "prompt_tokens >= 0 AND completion_tokens >= 0 AND total_tokens >= 0",
            name="ck_model_call_tokens",
        ),
    )


def turn_ownership_constraint(column="turn_id"):
    return ForeignKeyConstraint(
        [column, "organization_id", "owner_id"],
        ["alpendata_chat_turns.id", "alpendata_chat_turns.organization_id", "alpendata_chat_turns.owner_id"],
    )


class ToolRead(OwnedMixin, Base):
    __tablename__ = "alpendata_tool_reads"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    turn_id: Mapped[str] = mapped_column(String(36), index=True)
    capability: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(24), default="started")
    error_code: Mapped[str | None] = mapped_column(String(80))
    sources: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[int] = mapped_column(Integer, default=now)
    finished_at: Mapped[int | None] = mapped_column(Integer)
    __table_args__ = (
        turn_ownership_constraint(),
        CheckConstraint("status IN ('started', 'completed', 'failed')", name="ck_tool_read_status"),
    )


class RoutineProposal(OwnedMixin, Base):
    __tablename__ = "alpendata_routine_proposals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(String(36), index=True)
    template: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(160))
    benefit: Mapped[str] = mapped_column(Text)
    focus: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(2))
    created_at: Mapped[int] = mapped_column(Integer, default=now)
    __table_args__ = (
        ForeignKeyConstraint(
            ["conversation_id", "organization_id", "owner_id"],
            [
                "alpendata_conversations.id",
                "alpendata_conversations.organization_id",
                "alpendata_conversations.owner_id",
            ],
        ),
        UniqueConstraint("conversation_id", "template"),
        UniqueConstraint("id", "organization_id", "owner_id"),
    )


class RoutineTrial(OwnedMixin, Base):
    __tablename__ = "alpendata_routine_trials"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    proposal_id: Mapped[str] = mapped_column(String(36), index=True)
    turn_id: Mapped[str] = mapped_column(String(36), unique=True)
    created_at: Mapped[int] = mapped_column(Integer, default=now)
    __table_args__ = (
        turn_ownership_constraint(),
        ForeignKeyConstraint(
            ["proposal_id", "organization_id", "owner_id"],
            [
                "alpendata_routine_proposals.id",
                "alpendata_routine_proposals.organization_id",
                "alpendata_routine_proposals.owner_id",
            ],
        ),
    )
