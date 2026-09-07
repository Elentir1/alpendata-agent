from sqlalchemy import select
from test_chat import service as service

from alpendata_api.models import Conversation
from alpendata_api.organizations import add_member


def test_personal_projects_classification_and_frozen_context(service, account):
    app, client = service
    _, alice = account("alice@example.com")
    org = client.post("/api/organizations", headers=alice, json={"name": "Coaches"}).json()["id"]
    base = f"/api/organizations/{org}/chat"
    assert (
        client.put(
            f"/api/organizations/{org}/onboarding",
            headers=alice,
            json={
                "language": "fr",
                "role": "Coach",
                "needs": "Ateliers",
                "sector": "coaching",
                "success": "Préparer une séance pour mon équipe",
                "preferred_output": "presentation",
            },
        ).status_code
        == 200
    )
    project = client.post(
        base + "/projects",
        headers=alice,
        json={"name": "Client Exemple", "instructions": "Use concise workshop agendas."},
    ).json()
    chat = client.post(
        base + "/conversations", headers=alice, json={"language": "fr", "project_id": project["id"]}
    ).json()
    with app.state.session_factory() as db:
        before = db.get(Conversation, chat["id"]).system_prompt
        assert project["instructions"] in before
        assert "Préparer une séance pour mon équipe" in before
    assert (
        client.put(
            base + "/projects/" + project["id"],
            headers=alice,
            json={"name": "Client Renommé", "instructions": "Use detailed workshop agendas."},
        ).status_code
        == 200
    )
    assert (
        client.put(
            base + "/conversations/" + chat["id"],
            headers=alice,
            json={"title": "Atelier 100%", "project_id": None, "archived": True},
        ).status_code
        == 200
    )
    assert client.get(base, headers=alice).json()["conversations"] == []
    assert (
        client.get(base + "?archived=true&q=100%25&project=unfiled", headers=alice).json()["conversations"][
            0
        ]["id"]
        == chat["id"]
    )
    assert client.get(base + "?archived=true&q=_", headers=alice).json()["conversations"] == []
    assert (
        client.put(
            base + "/conversations/" + chat["id"],
            headers=alice,
            json={"title": "Atelier", "project_id": project["id"], "archived": False},
        ).status_code
        == 200
    )
    assert (
        client.get(base + "?project=" + project["id"], headers=alice).json()["conversations"][0]["id"]
        == chat["id"]
    )
    with app.state.session_factory() as db:
        assert db.get(Conversation, chat["id"]).system_prompt == before
    newer = client.post(base + "/conversations", headers=alice, json={"project_id": project["id"]}).json()
    with app.state.session_factory() as db:
        assert "Use detailed workshop agendas." in db.get(Conversation, newer["id"]).system_prompt


def test_projects_never_expose_other_members_context(service, account):
    app, client = service
    _, admin = account("admin@example.com")
    bob_id, bob = account("bob@example.com")
    org = client.post("/api/organizations", headers=admin, json={"name": "Coaches"}).json()["id"]
    with app.state.session_factory.begin() as db:
        add_member(db, org, bob_id, "member")
    base = f"/api/organizations/{org}/chat"
    for headers in (admin, bob):
        client.put(
            f"/api/organizations/{org}/onboarding",
            headers=headers,
            json={"language": "fr", "role": "Coach", "needs": "Prepare sessions"},
        )
    private = client.post(
        base + "/projects", headers=bob, json={"name": "Private client", "instructions": "Bob only"}
    ).json()
    chat = client.post(base + "/conversations", headers=admin, json={}).json()
    assert client.get(base + "/projects", headers=admin).json() == {"projects": []}
    assert client.get(base + "?project=" + private["id"], headers=admin).status_code == 404
    assert (
        client.post(base + "/conversations", headers=admin, json={"project_id": private["id"]}).status_code
        == 404
    )
    assert (
        client.put(base + "/projects/" + private["id"], headers=admin, json={"name": "Take over"}).status_code
        == 404
    )
    assert (
        client.put(
            base + "/conversations/" + chat["id"],
            headers=admin,
            json={"title": "Move", "project_id": private["id"]},
        ).status_code
        == 404
    )
    with app.state.session_factory() as db:
        assert db.scalar(select(Conversation).where(Conversation.id == chat["id"])).project_id is None
