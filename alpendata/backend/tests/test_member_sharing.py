import base64
from uuid import uuid4

from test_company_resources import publication
from test_documents import example_pdf, start_document_turn
from test_routines import connected_service as connected_service
from test_routines import routine_service as routine_service

from alpendata_api.auth import issue_session
from alpendata_api.chat_worker import ChatWorker
from alpendata_api.models import User
from alpendata_api.organizations import add_member


def sharing_author(app, org):
    with app.state.session_factory.begin() as db:
        user = User(issuer="https://identity.example.test", subject=str(uuid4()), display_name="Colleague")
        db.add(user)
        db.flush()
        add_member(db, org, user.id, "member")
        return user.id, {"Authorization": "Bearer " + issue_session(db, user, 3600)}


def test_members_publish_and_control_their_copies_without_acquiring_a_readers_administration(routine_service):
    app, client, _, _, _, org, admin, author = routine_service
    reader_id, reader = sharing_author(app, org)
    base = f"/api/organizations/{org}/company-resources"
    directory = client.get(base + "/recipients", headers=author[2])
    assert directory.status_code == 200
    assert directory.json()["current_user_id"] == author[0]
    assert all(
        set(row) == {"user_id", "display_name", "role", "active"} for row in directory.json()["members"]
    )
    assert {row["user_id"] for row in directory.json()["members"]} == {admin[0], author[0], reader_id}
    assert client.get(f"/api/organizations/{org}/members", headers=author[2]).status_code == 403
    foreign = client.post("/api/organizations", headers=admin[2], json={"name": "Other company"}).json()["id"]
    assert (
        client.get(f"/api/organizations/{foreign}/company-resources/recipients", headers=reader).status_code
        == 404
    )
    body = publication(member_ids=[reader_id])
    response = client.post(base, headers=author[2], json=body)
    assert response.status_code == 201, response.text
    row = response.json()
    assert row["created_by"] == author[0] and row["can_manage"]
    assert client.post(base, headers=author[2], json={**body, "source_document_id": None}).json() == row
    path = base + "/" + row["id"]
    assert client.get(path, headers=author[2]).json()["can_manage"]
    assert client.get(path, headers=admin[2]).json()["can_manage"]
    read = client.get(path, headers=reader).json()
    assert not read["can_manage"] and "member_ids" not in read
    change = {k: v for k, v in {**body, "version": row["version"]}.items() if k != "request_id"}
    assert client.put(path, headers=reader, json=change).status_code == 404
    assert (
        client.patch(
            path + "/access", headers=reader, json={"version": 1, "audience": "team", "confirmed": True}
        ).status_code
        == 404
    )
    assert client.request("DELETE", path, headers=reader, json={"version": 1}).status_code == 404
    restricted = client.patch(
        path + "/access",
        headers=author[2],
        json={"version": 1, "audience": "selected", "member_ids": [], "confirmed": True},
    ).json()
    assert client.get(path, headers=reader).status_code == 404
    assert client.get(path, headers=author[2]).status_code == 200
    revised = client.put(
        path,
        headers=admin[2],
        json={**change, "version": restricted["version"], "text": "Reviewed company copy"},
    ).json()
    assert (
        client.put(path, headers=author[2], json={**change, "version": restricted["version"]}).status_code
        == 409
    )
    assert client.get(path, headers=author[2]).json()["text"] == "Reviewed company copy"
    assert (
        client.request("DELETE", path, headers=admin[2], json={"version": revised["version"]}).status_code
        == 204
    )
    assert client.get(path, headers=author[2]).status_code == 404
    assert client.post(base, headers=author[2], json=body).status_code == 409
    assert (
        client.patch(
            f"/api/organizations/{org}/members/{author[0]}",
            headers=admin[2],
            json={"version": 1, "active": False, "licensed": True, "role": "member"},
        ).status_code
        == 200
    )
    assert client.get(base + "/recipients", headers=author[2]).status_code == 404
    assert client.post(base, headers=author[2], json=publication()).status_code == 404


def test_sharing_a_chat_document_copies_only_the_current_users_immutable_artifact(routine_service):
    app, client, settings, _, _, org, admin, author = routine_service
    _, reader = sharing_author(app, org)
    base = f"/api/organizations/{org}"
    path = start_document_turn(routine_service)
    worker = ChatWorker(settings, app.state.session_factory, runtime=object(), microsoft=object())
    job = worker.claim()
    content = example_pdf()
    reply = worker.tool(
        job,
        [],
        {"kind": "document", "filename": "Session.pdf", "content_base64": base64.b64encode(content).decode()},
    )
    assert reply["status"] == 200
    original = reply["body"]
    worker.finish(job, result={"response": "The document was created."})
    body = publication(
        kind="document", text="", title="Shared session", source_document_id=original["id"], audience="team"
    )
    assert client.post(base + "/company-resources", headers=admin[2], json=body).status_code == 404
    assert client.post(base + "/company-resources", headers=reader, json=body).status_code == 404
    assert (
        client.post(
            base + "/company-resources",
            headers=author[2],
            json={
                **body,
                "document": {"filename": "Session.pdf", "content_base64": base64.b64encode(content).decode()},
            },
        ).status_code
        == 422
    )
    assert (
        client.patch(
            base + "/members/" + author[0],
            headers=admin[2],
            json={"version": 1, "role": "member", "active": True, "licensed": False},
        ).status_code
        == 200
    )
    # Sharing an existing document needs personal ownership, not a new model execution.
    shared = client.post(base + "/company-resources", headers=author[2], json=body)
    assert shared.status_code == 201, shared.text
    copied = shared.json()
    assert copied["sha256"] == original["sha256"] and "source_document_id" not in copied
    assert client.post(base + "/company-resources", headers=author[2], json=body).json() == copied
    assert (
        client.get(
            base + f"/company-resources/{copied['id']}/download?version={copied['version']}", headers=reader
        ).content
        == content
    )
    assert client.get(base + f"/documents/{original['id']}/download", headers=reader).status_code == 404
    assert client.get(path, headers=reader).status_code == 404
    assert client.get(base + f"/documents/{original['id']}/download", headers=author[2]).content == content
    assert (
        client.request(
            "DELETE",
            base + "/company-resources/" + copied["id"],
            headers=author[2],
            json={"version": copied["version"]},
        ).status_code
        == 204
    )
    assert client.get(base + f"/documents/{original['id']}/download", headers=author[2]).content == content
    foreign = client.post("/api/organizations", headers=author[2], json={"name": "Other"}).json()["id"]
    assert (
        client.post(
            f"/api/organizations/{foreign}/company-resources",
            headers=author[2],
            json={**body, "request_id": str(uuid4())},
        ).status_code
        == 404
    )
