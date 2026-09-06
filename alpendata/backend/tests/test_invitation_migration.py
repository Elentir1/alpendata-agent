from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData, Table, select

from alpendata_api.database import database_factory
from alpendata_api.models import Invitation, InvitationProof


def test_upgrade_preserves_existing_invitation_and_mailbox_proof(database_url):
    engine, factory = database_factory(database_url)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    owner, org, invitation, proof = (str(uuid4()) for _ in range(4))
    try:
        with engine.begin() as db:
            config.attributes["connection"] = db
            command.upgrade(config, "0018")
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
                "alpendata_invitations": dict(
                    id=invitation,
                    organization_id=org,
                    recipient_email="other@example.com",
                    token_hash="a" * 64,
                    expires_at=2000000000,
                    revoked=False,
                    inviter_id=owner,
                ),
                "alpendata_invitation_proofs": dict(
                    id=proof,
                    invitation_id=invitation,
                    user_id=owner,
                    token_hash="b" * 64,
                    created_at=1800000000,
                    expires_at=1800000900,
                ),
            }
            for name, values in rows.items():
                table = Table(name, MetaData(), autoload_with=db)
                db.execute(table.insert().values(**values))
        with engine.begin() as db:
            config.attributes["connection"] = db
            command.upgrade(config, "head")
            command.check(config)
        with factory() as db:
            item = db.get(Invitation, invitation)
            assert item.token_hash == "a" * 64 and item.delivery_status == "manual"
            assert item.delivery_request_id is None
            assert db.get(InvitationProof, proof).token_hash == "b" * 64
            assert db.scalar(select(InvitationProof.invitation_id)) == item.id
    finally:
        engine.dispose()
