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
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    false,
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


class OrganizationPolicy(Base):
    __tablename__ = "alpendata_organization_policies"
    organization_id: Mapped[str] = mapped_column(ForeignKey("alpendata_organizations.id"), primary_key=True)
    allowed_capabilities: Mapped[list] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_by: Mapped[str] = mapped_column(ForeignKey("alpendata_users.id"))
    updated_at: Mapped[int] = mapped_column(Integer, default=now)
    __table_args__ = (CheckConstraint("version > 0", name="ck_organization_policy_version"),)


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


class PersonalActionPolicy(OwnedMixin, Base):
    __tablename__ = "alpendata_personal_action_policies"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email_mode: Mapped[str] = mapped_column(String(16), default="confirm")
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[int] = mapped_column(Integer, default=now)
    __table_args__ = (
        ownership_constraint(),
        UniqueConstraint("organization_id", "owner_id"),
        CheckConstraint("email_mode IN ('confirm', 'automatic')", name="ck_personal_email_mode"),
        CheckConstraint("version > 0", name="ck_personal_action_version"),
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
    documents_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    tool_revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    email_send_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    email_delivery: Mapped[dict | None] = mapped_column(JSON, nullable=True)
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


class Artifact(OwnedMixin, Base):
    __tablename__ = "alpendata_artifacts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    turn_id: Mapped[str] = mapped_column(String(36), index=True)
    filename: Mapped[str] = mapped_column(String(180))
    media_type: Mapped[str] = mapped_column(String(120))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    content: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    created_at: Mapped[int] = mapped_column(Integer, default=now)
    __table_args__ = (
        turn_ownership_constraint(),
        UniqueConstraint("turn_id", "filename", "sha256"),
        UniqueConstraint("id", "organization_id", "owner_id", name="uq_artifact_owner"),
        CheckConstraint("size > 0 AND size <= 5242880", name="ck_artifact_size"),
    )


class SharePointSave(OwnedMixin, Base):
    __tablename__ = "alpendata_sharepoint_saves"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    artifact_id: Mapped[str] = mapped_column(String(36), index=True)
    drive_id: Mapped[str] = mapped_column(String(512))
    folder_id: Mapped[str] = mapped_column(String(512))
    folder_name: Mapped[str] = mapped_column(String(1024))
    folder_url: Mapped[str | None] = mapped_column(String(4096))
    filename: Mapped[str] = mapped_column(String(180))
    existing_id: Mapped[str | None] = mapped_column(String(512))
    existing_etag: Mapped[str | None] = mapped_column(String(1024))
    status: Mapped[str] = mapped_column(String(24), default="review")
    error_code: Mapped[str | None] = mapped_column(String(80))
    result: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[int] = mapped_column(Integer, default=now)
    expires_at: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[int | None] = mapped_column(Integer)
    finished_at: Mapped[int | None] = mapped_column(Integer)
    __table_args__ = (
        ForeignKeyConstraint(
            ["artifact_id", "organization_id", "owner_id"],
            ["alpendata_artifacts.id", "alpendata_artifacts.organization_id", "alpendata_artifacts.owner_id"],
            name="fk_sharepoint_save_artifact_owner",
        ),
        CheckConstraint(
            "status IN ('review', 'running', 'completed', 'failed', 'unknown')",
            name="ck_sharepoint_save_status",
        ),
    )


class EmailDraft(OwnedMixin, Base):
    __tablename__ = "alpendata_email_drafts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    turn_id: Mapped[str] = mapped_column(String(36), index=True)
    initial_hash: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, default=1)
    message: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[int] = mapped_column(Integer, default=now)
    updated_at: Mapped[int] = mapped_column(Integer, default=now)
    __table_args__ = (
        turn_ownership_constraint(),
        UniqueConstraint("turn_id", "initial_hash"),
        UniqueConstraint("id", "organization_id", "owner_id", name="uq_email_draft_owner"),
        CheckConstraint("version > 0", name="ck_email_draft_version"),
    )


class EmailAttempt(OwnedMixin, Base):
    __tablename__ = "alpendata_email_attempts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    draft_id: Mapped[str] = mapped_column(String(36), index=True)
    version: Mapped[int] = mapped_column(Integer)
    message: Mapped[dict] = mapped_column(JSON)
    correlation_id: Mapped[str | None] = mapped_column(String(36))
    verification: Mapped[dict | None] = mapped_column(JSON)
    initiator: Mapped[str] = mapped_column(String(16), default="browser", server_default="browser")
    autonomy_version: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), default="sending")
    error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[int] = mapped_column(Integer, default=now)
    finished_at: Mapped[int | None] = mapped_column(Integer)
    __table_args__ = (
        ForeignKeyConstraint(
            ["draft_id", "organization_id", "owner_id"],
            [
                "alpendata_email_drafts.id",
                "alpendata_email_drafts.organization_id",
                "alpendata_email_drafts.owner_id",
            ],
            name="fk_email_attempt_draft_owner",
        ),
        UniqueConstraint("draft_id", "version"),
        CheckConstraint(
            "status IN ('sending', 'accepted', 'failed', 'unknown')", name="ck_email_attempt_status"
        ),
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


class RoutineSchedule(OwnedMixin, Base):
    __tablename__ = "alpendata_routine_schedules"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    proposal_id: Mapped[str] = mapped_column(String(36), unique=True)
    reviewed_turn_id: Mapped[str] = mapped_column(String(36))
    activation_request_id: Mapped[str] = mapped_column(String(36))
    frequency: Mapped[str] = mapped_column(String(16))
    local_time: Mapped[str] = mapped_column(String(5))
    timezone: Mapped[str] = mapped_column(String(100))
    weekday: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(16), default="active")
    next_run_at: Mapped[int | None] = mapped_column(Integer, index=True)
    reason_code: Mapped[str | None] = mapped_column(String(80))
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[int] = mapped_column(Integer, default=now)
    updated_at: Mapped[int] = mapped_column(Integer, default=now)
    __table_args__ = (
        turn_ownership_constraint("reviewed_turn_id"),
        ForeignKeyConstraint(
            ["proposal_id", "organization_id", "owner_id"],
            [
                "alpendata_routine_proposals.id",
                "alpendata_routine_proposals.organization_id",
                "alpendata_routine_proposals.owner_id",
            ],
        ),
        UniqueConstraint("id", "organization_id", "owner_id"),
        UniqueConstraint("organization_id", "owner_id", "activation_request_id"),
        CheckConstraint(
            "status IN ('active', 'paused', 'blocked', 'archived')", name="ck_routine_schedule_status"
        ),
        CheckConstraint("frequency IN ('daily', 'weekdays', 'weekly')", name="ck_routine_schedule_frequency"),
        CheckConstraint(
            "weekday >= 0 AND weekday <= 6 AND version > 0 AND failure_count >= 0",
            name="ck_routine_schedule_values",
        ),
    )


class RoutineOccurrence(OwnedMixin, Base):
    __tablename__ = "alpendata_routine_occurrences"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    schedule_id: Mapped[str] = mapped_column(String(36), index=True)
    schedule_version: Mapped[int] = mapped_column(Integer)
    scheduled_for: Mapped[int] = mapped_column(Integer)
    outcome: Mapped[str] = mapped_column(String(24))
    turn_id: Mapped[str | None] = mapped_column(String(36), unique=True)
    created_at: Mapped[int] = mapped_column(Integer, default=now)
    __table_args__ = (
        turn_ownership_constraint(),
        ForeignKeyConstraint(
            ["schedule_id", "organization_id", "owner_id"],
            [
                "alpendata_routine_schedules.id",
                "alpendata_routine_schedules.organization_id",
                "alpendata_routine_schedules.owner_id",
            ],
        ),
        UniqueConstraint("schedule_id", "scheduled_for"),
        CheckConstraint("outcome IN ('queued', 'missed')", name="ck_routine_occurrence_outcome"),
        CheckConstraint(
            "(outcome = 'queued' AND turn_id IS NOT NULL) OR (outcome = 'missed' AND turn_id IS NULL)",
            name="ck_routine_occurrence_turn",
        ),
    )
