"""Onboarding proposals and explicitly requested, private, single-run trials."""

import json
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field
from sqlalchemy import select

from .access import owned
from .auth import authenticate, request_authorization
from .chat import (
    connected_capabilities,
    conversation_view,
    create_conversation,
    queue_turn,
    request_turn,
    turn_view,
)
from .connections import lock_member
from .models import Conversation, RoutineProposal, RoutineTrial
from .routine_catalog import RECIPES, available_recipes
from .routine_service import trial_view
from .schemas import Input

PREFIX = "/api/organizations/{organization_id}"


class PlanningInput(Input):
    request_id: UUID
    language: Literal["fr", "en"] = "fr"
    refinement: str = Field(min_length=1, max_length=4000)


class TrialInput(Input):
    request_id: UUID


def routines_router(settings, factory):
    router = APIRouter()

    def actor(db, request, organization_id):
        user = authenticate(db, request_authorization(request, settings))
        lock_member(db, user, organization_id)
        return user

    @router.post(PREFIX + "/onboarding/proposals", status_code=202)
    def propose(organization_id: str, request: Request, body: PlanningInput):
        with factory.begin() as db:
            user = actor(db, request, organization_id)
            previous = request_turn(db, user, organization_id, body.request_id)
            if previous:
                conversation = db.get(Conversation, previous.conversation_id)
                if (
                    conversation.purpose != "onboarding"
                    or previous.message != body.refinement
                    or conversation.language != body.language
                ):
                    raise HTTPException(409, "chat_request_conflict")
                return {"conversation": conversation_view(conversation), "turn": turn_view(previous)}
            recipes = available_recipes(connected_capabilities(db, user, organization_id))
            if len(recipes) < 2:
                raise HTTPException(409, "microsoft_reconnect_required")
            catalog = {
                name: {"description": item.instruction, "sources": item.capabilities}
                for name, item in recipes.items()
            }
            prompt = (
                "Help the user find their first useful workplace tasks. Use their profile and message to "
                "personalize "
                "2 or 3 distinct proposals from this catalog. Call alpendata_propose_routines to save them. "
                "Use concise titles and benefits in the conversation language, "
                "and concrete focus instructions. "
                "Do not execute a trial or activate recurrence: "
                "the user chooses a proposal with the trial button. "
                "One immutable batch is saved per conversation; "
                "a new planning conversation can replace the selection. "
                "Catalog: " + json.dumps(catalog, ensure_ascii=False)
            )
            conversation = create_conversation(
                db,
                settings,
                user,
                organization_id,
                body.language,
                "Mes premières tâches" if body.language == "fr" else "My first tasks",
                purpose="onboarding",
                extra_prompt=prompt,
            )
            turn = queue_turn(db, settings, user, conversation, body.request_id, body.refinement)
            return {"conversation": conversation_view(conversation), "turn": turn_view(turn)}

    @router.post(PREFIX + "/routines/{proposal_id}/trial", status_code=202)
    def trial(organization_id: str, proposal_id: str, request: Request, body: TrialInput):
        with factory.begin() as db:
            user = actor(db, request, organization_id)
            proposal = owned(db, RoutineProposal, organization_id, user.id, proposal_id)
            previous = request_turn(db, user, organization_id, body.request_id)
            if previous:
                saved = db.scalar(select(RoutineTrial).where(RoutineTrial.turn_id == previous.id))
                if saved is None or saved.proposal_id != proposal.id:
                    raise HTTPException(409, "chat_request_conflict")
                return trial_view(db, saved)
            recipe = RECIPES[proposal.template]
            prompt = (
                "Perform this task once using the required Microsoft sources. "
                + recipe.instruction
                + " State what was actually consulted and any missing information. No recurrence is active. "
                + "Personal focus data: "
                + json.dumps(proposal.focus, ensure_ascii=False)
            )
            conversation = create_conversation(
                db,
                settings,
                user,
                organization_id,
                proposal.language,
                proposal.title,
                purpose="routine_trial",
                capabilities=recipe.capabilities,
                extra_prompt=prompt,
            )
            message = "Tester cette tâche une fois." if proposal.language == "fr" else "Try this task once."
            turn = queue_turn(db, settings, user, conversation, body.request_id, message)
            saved = RoutineTrial(
                organization_id=organization_id, owner_id=user.id, proposal_id=proposal.id, turn_id=turn.id
            )
            db.add(saved)
            db.flush()
            return trial_view(db, saved)

    return router
