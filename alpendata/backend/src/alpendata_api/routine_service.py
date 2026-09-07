"""Personal proposals and evidence from broker reads, never from model assertions."""

from fastapi import HTTPException
from pydantic import Field
from sqlalchemy import select

from .action_policy import email_autonomy_available
from .graph import web_link
from .models import (
    ChatTurn,
    Conversation,
    MicrosoftConnection,
    RoutineProposal,
    RoutineSchedule,
    RoutineTrial,
    ToolRead,
)
from .organization_policy import allowed_capabilities
from .routine_catalog import RECIPES, available_recipes
from .routine_delivery import delivery_accepted
from .schemas import Input


class ProposalInput(Input):
    template: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=160)
    benefit: str = Field(min_length=1, max_length=1000)
    focus: str = Field(min_length=1, max_length=2000)


class ProposalsInput(Input):
    proposals: list[ProposalInput] = Field(min_length=2, max_length=3)


def proposal_view(item):
    return {
        **{key: getattr(item, key) for key in ("id", "template", "title", "benefit", "focus", "language")},
        "sends_email": RECIPES[item.template].sends_email,
    }


def record_proposals(db, turn, payload):
    data = ProposalsInput.model_validate(payload)
    conversation = db.get(Conversation, turn.conversation_id)
    if conversation.purpose != "onboarding":
        raise HTTPException(403, "routine_planning_not_available")
    from .models import InfomaniakConnection

    connection_model = (
        InfomaniakConnection if conversation.integration_provider == "infomaniak" else MicrosoftConnection
    )
    connection = db.scalar(
        select(connection_model).where(
            connection_model.organization_id == turn.organization_id,
            connection_model.owner_id == turn.owner_id,
        )
    )
    current = connection.capabilities if connection and connection.status == "connected" else []
    available = available_recipes(
        set(current) & set(conversation.capabilities) & set(allowed_capabilities(db, turn.organization_id)),
        email_autonomy=email_autonomy_available(
            db, turn.organization_id, turn.owner_id, conversation.integration_provider
        ),
    )
    names = [item.template for item in data.proposals]
    if len(set(names)) != len(names) or any(name not in available for name in names):
        raise HTTPException(409, "routine_capabilities_changed")
    rows = db.scalars(select(RoutineProposal).where(RoutineProposal.conversation_id == conversation.id)).all()
    if rows:
        # A proposal that may already have been tried remains immutable.
        return {"proposals": [proposal_view(row) for row in rows], "already_saved": True}
    for item in data.proposals:
        row = RoutineProposal(
            organization_id=turn.organization_id,
            owner_id=turn.owner_id,
            conversation_id=conversation.id,
            language=conversation.language,
            **item.model_dump(),
        )
        db.add(row)
        rows.append(row)
    db.flush()
    return {"proposals": [proposal_view(row) for row in rows], "already_saved": False}


def source_references(capability, result):
    collection, label = {
        "mail": ("messages", "subject"),
        "calendar": ("events", "subject"),
        "files": ("files", "name"),
    }[capability]
    return [
        {"kind": capability, "label": str(item.get(label) or "")[:500], "url": web_link(item.get("url"))}
        for item in result.get(collection, [])[:20]
    ]


def read_evidence(db, turn):
    rows = db.scalars(
        select(ToolRead)
        .where(
            ToolRead.turn_id == turn.id,
            ToolRead.organization_id == turn.organization_id,
            ToolRead.owner_id == turn.owner_id,
            ToolRead.status == "completed",
        )
        .order_by(ToolRead.created_at, ToolRead.id)
    ).all()
    sources, seen = [], set()
    for row in rows:
        for item in row.sources:
            key = (item["kind"], item["label"], item["url"])
            if key not in seen:
                sources.append(item)
                seen.add(key)
    return {row.capability for row in rows}, sources


def trial_view(db, trial):
    turn = db.get(ChatTurn, trial.turn_id)
    proposal = db.get(RoutineProposal, trial.proposal_id)
    reads, _ = read_evidence(db, turn)
    schedule = db.scalar(
        select(RoutineSchedule).where(
            RoutineSchedule.proposal_id == trial.proposal_id, RoutineSchedule.status != "archived"
        )
    )
    return {
        "id": trial.id,
        "proposal_id": trial.proposal_id,
        "conversation_id": turn.conversation_id,
        "turn_id": turn.id,
        "schedule_id": schedule.id if schedule else None,
        "schedule_version": schedule.version if schedule else None,
        "can_replace_schedule": bool(schedule and schedule.reviewed_turn_id != trial.turn_id),
        "status": turn.status,
        "email_delivery": db.get(Conversation, turn.conversation_id).email_delivery,
        "delivery_accepted": delivery_accepted(db, turn),
        "requires_sources": bool(RECIPES[proposal.template].capabilities),
        "sources_verified": turn.status == "completed"
        and set(RECIPES[proposal.template].capabilities) <= reads,
    }


def conversation_routines(db, conversation):
    proposals = db.scalars(
        select(RoutineProposal)
        .where(
            RoutineProposal.organization_id == conversation.organization_id,
            RoutineProposal.owner_id == conversation.owner_id,
            RoutineProposal.conversation_id == conversation.id,
        )
        .order_by(RoutineProposal.created_at, RoutineProposal.id)
    ).all()
    trials = db.scalars(
        select(RoutineTrial)
        .join(ChatTurn, RoutineTrial.turn_id == ChatTurn.id)
        .where(
            RoutineTrial.organization_id == conversation.organization_id,
            RoutineTrial.owner_id == conversation.owner_id,
            ChatTurn.conversation_id == conversation.id,
        )
    ).all()
    return {
        "proposals": [proposal_view(row) for row in proposals],
        "trials": [trial_view(db, row) for row in trials],
    }
