from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData, Table, func, select

from alpendata_api.database import database_factory
from alpendata_api.models import ChatTurn, Conversation, PersonalResource, Project, ProjectEntry


def test_workspace_upgrade_preserves_populated_projects_history_and_private_notes(database_url):
    engine, factory = database_factory(database_url)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    owner, org, project, conversation, turn, note = (str(uuid4()) for _ in range(6))
    try:
        with engine.begin() as db:
            config.attributes["connection"] = db
            command.upgrade(config, "0023")
            rows = {
                "alpendata_users": dict(
                    id=owner,
                    issuer="test",
                    subject="coach",
                    verified_email="coach@example.com",
                    display_name="Coach",
                    active=True,
                ),
                "alpendata_organizations": dict(id=org, name="Coaches", seat_capacity=3),
                "alpendata_memberships": dict(
                    organization_id=org, user_id=owner, role="admin", active=True, licensed=True, version=1
                ),
                "alpendata_projects": dict(
                    id=project,
                    organization_id=org,
                    owner_id=owner,
                    name="Private client",
                    instructions="Confidential brief",
                    created_at=1800000000,
                ),
                "alpendata_conversations": dict(
                    id=conversation,
                    organization_id=org,
                    owner_id=owner,
                    title="Client meeting",
                    project_id=project,
                    archived=False,
                    purpose="chat",
                    documents_enabled=True,
                    tool_revision=6,
                    email_send_enabled=False,
                    language="fr",
                    provider="mistral",
                    model="old-model",
                    system_prompt="Original frozen prefix",
                    capabilities=["mail"],
                    created_at=1800000000,
                ),
                "alpendata_chat_turns": dict(
                    id=turn,
                    organization_id=org,
                    owner_id=owner,
                    conversation_id=conversation,
                    request_id=str(uuid4()),
                    sequence=1,
                    message="Previous question",
                    response="Previous response",
                    status="completed",
                    cancel_requested=False,
                    created_at=1800000000,
                    started_at=1800000000,
                    finished_at=1800000001,
                ),
                "alpendata_personal_resources": dict(
                    id=note,
                    organization_id=org,
                    owner_id=owner,
                    kind="memory",
                    title="Private note",
                    content="Another client's private note",
                    created_at=1800000000,
                ),
            }
            for name, values in rows.items():
                table = Table(name, MetaData(), autoload_with=db)
                # Fixture fields explicitly supplied above; no current ORM defaults may change old data.
                db.execute(table.insert().values(**values))
        with engine.begin() as db:
            config.attributes["connection"] = db
            command.upgrade(config, "head")
            command.check(config)
        with factory() as db:
            item = db.get(Conversation, conversation)
            assert item.parent_id is None and item.context_project_id == project
            assert item.system_prompt == "Original frozen prefix" and item.tool_revision == 6
            assert item.work_settings is None and item.service_features is None
            assert db.get(Project, project).owner_id == owner
            assert db.get(ChatTurn, turn).response == "Previous response"
            assert db.get(PersonalResource, note).content == "Another client's private note"
            assert db.scalar(select(func.count()).select_from(ProjectEntry)) == 0
    finally:
        engine.dispose()
