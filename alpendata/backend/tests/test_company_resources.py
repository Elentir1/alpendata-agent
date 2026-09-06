import base64
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic, sleep
from uuid import uuid4

from sqlalchemy import select, text
from test_documents import example_pdf, start_document_turn
from test_routines import connected_service as connected_service
from test_routines import routine_service as routine_service

from alpendata_api.chat_worker import ChatWorker
from alpendata_api.connections import lock_member
from alpendata_api.models import CompanyResource, Conversation, User


def publication(**changes):
    return {
        "request_id": str(uuid4()),
        "title": "Shared coaching guidelines",
        "kind": "note",
        "text": "Start each workshop with the client's agreed objectives.",
        "audience": "selected",
        "member_ids": [],
        "confirmed": True,
        **changes,
    }


def test_company_copies_require_explicit_publication_and_personal_grants(routine_service):
    app, client, _, _, _, org, admin, owner = routine_service
    base = f"/api/organizations/{org}/company-resources"
    body = publication(member_ids=[owner[0]])
    assert client.post(base, headers=owner[2], json={**body, "created_by": admin[0]}).status_code == 422
    assert client.post(base, headers=admin[2], json={**body, "confirmed": False}).status_code == 422
    assert client.post(base, headers=admin[2], json={**body, "member_ids": [str(uuid4())]}).status_code == 422
    result = client.post(base, headers=admin[2], json=body)
    assert result.status_code == 201, result.text
    note = result.json()
    assert client.post(base, headers=admin[2], json=body).json() == note
    assert client.post(base, headers=admin[2], json={**body, "text": "Changed request"}).status_code == 409
    read = client.get(base + "/" + note["id"], headers=owner[2])
    assert read.json()["text"] == body["text"] and "member_ids" not in read.json()
    assert read.headers["Cache-Control"] == "no-store"
    assert client.get(base + "?query=coaching", headers=owner[2]).json()["resources"][0]["id"] == note["id"]
    assert client.get(base + "?query=%", headers=owner[2]).json()["resources"] == []
    other = client.post("/api/organizations", headers=admin[2], json={"name": "Other"}).json()["id"]
    assert (
        client.get(f"/api/organizations/{other}/company-resources/{note['id']}", headers=admin[2]).status_code
        == 404
    )
    path = base + "/" + note["id"]
    restricted = client.patch(
        path + "/access",
        headers=admin[2],
        json={"version": note["version"], "audience": "selected", "member_ids": [], "confirmed": True},
    ).json()
    assert client.get(path, headers=owner[2]).status_code == 404
    assert client.get(base, headers=owner[2]).json()["resources"] == []
    assert (
        client.put(
            path,
            headers=admin[2],
            json={k: v for k, v in {**body, "version": note["version"]}.items() if k != "request_id"},
        ).status_code
        == 409
    )
    updated = client.put(
        path,
        headers=admin[2],
        json={
            k: v
            for k, v in {
                **body,
                "version": restricted["version"],
                "text": "Updated guidance",
                "audience": "team",
                "member_ids": [],
            }.items()
            if k != "request_id"
        },
    )
    assert updated.status_code == 200
    assert client.get(path, headers=owner[2]).json()["text"] == "Updated guidance"
    document = publication(
        kind="document",
        text="",
        title="Workshop template",
        audience="team",
        document={"filename": "Workshop.pdf", "content_base64": base64.b64encode(example_pdf()).decode()},
    )
    file = client.post(base, headers=admin[2], json=document).json()
    download = base + f"/{file['id']}/download?version={file['version']}"
    assert client.get(download, headers=owner[2]).content == example_pdf()
    assert client.get(download + "0", headers=owner[2]).status_code == 409
    assert "attachment" in client.get(download, headers=owner[2]).headers["Content-Disposition"]
    assert (
        client.post(
            base,
            headers=admin[2],
            json=publication(
                kind="document", text="", document={"filename": "bad.pdf", "content_base64": "aW52YWxpZA=="}
            ),
        ).status_code
        == 400
    )
    assert (
        client.request(
            "DELETE", base + "/" + file["id"], headers=admin[2], json={"version": file["version"]}
        ).status_code
        == 204
    )
    assert client.get(download, headers=owner[2]).status_code == 404
    with app.state.session_factory() as db:
        retired = db.get(CompanyResource, file["id"])
        assert not retired.active and retired.content is None and retired.size == 0


def test_grant_revocation_waits_for_current_read_and_broker_checks_current_revision(routine_service):
    app, client, settings, _, _, org, admin, owner = routine_service
    base = f"/api/organizations/{org}/company-resources"
    note = client.post(base, headers=admin[2], json=publication(member_ids=[owner[0]])).json()
    path = start_document_turn(routine_service)
    worker = ChatWorker(settings, app.state.session_factory, runtime=object(), microsoft=object())
    job = worker.claim()
    request = {
        "kind": "company_resource",
        "action": "read",
        "resource_id": note["id"],
        "version": note["version"],
    }
    assert worker.tool(job, [], request)["status"] == 200
    with app.state.session_factory.begin() as db:
        conversation = db.scalar(select(Conversation).where(Conversation.id == path.split("/")[-1]))
        conversation.tool_revision = 4
    assert worker.tool(job, [], request)["status"] == 403
    with app.state.session_factory.begin() as db:
        db.get(Conversation, path.split("/")[-1]).tool_revision = 5
    entered, release = Event(), Event()
    reader_pid = []

    def current_read():
        with app.state.session_factory.begin() as db:
            lock_member(db, db.get(User, owner[0]), org)
            if db.bind.dialect.name == "postgresql":
                reader_pid.append(db.scalar(text("SELECT pg_backend_pid()")))
            entered.set()
            assert release.wait(15)

    def revoke():
        assert entered.wait(15)
        return client.patch(
            base + "/" + note["id"] + "/access",
            headers=admin[2],
            json={"version": note["version"], "audience": "selected", "member_ids": [], "confirmed": True},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        reading = pool.submit(current_read)
        assert entered.wait(15)
        changing = pool.submit(revoke)
        try:
            if reader_pid:
                deadline = monotonic() + 10
                blocked = False
                while monotonic() < deadline:
                    with app.state.engine.connect() as connection:
                        blocked = connection.scalar(
                            text(
                                "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                                "WHERE :reader = ANY(pg_blocking_pids(pid)))"
                            ),
                            {"reader": reader_pid[0]},
                        )
                    if blocked:
                        break
                    sleep(0.02)
                assert blocked, "Revocation must wait for the current owner's read transaction"
        finally:
            release.set()
        reading.result(timeout=20)
        response = changing.result(timeout=20)
    assert response.status_code == 200, response.text
    assert worker.tool(job, [], request)["status"] == 404
    assert worker.tool(job, [], {"kind": "company_resource", "action": "search"})["body"]["resources"] == []
    assert worker.tool(job, [], {**request, "owner_id": admin[0]})["status"] == 400
    worker.finish(job, result={"response": "The company resource is no longer shared."})
