from uuid import uuid4

import pytest
from test_microsoft_connections import CALLBACK, connected_service  # noqa: F401

from alpendata_api.accounts import provision
from alpendata_api.auth import issue_session
from alpendata_api.models import User

pytestmark = pytest.mark.usefixtures("connected_service")


def test_password_owner_connects_microsoft_separately_and_cannot_silently_switch_source(request):
    app, client, settings, server, graph, org, alice, bob = request.getfixturevalue("connected_service")
    with app.state.session_factory.begin() as db:
        account, _ = provision(db, "independent@example.com", "Independent", organization_id=org)
        user_id = account.user_id
        auth = {"Authorization": "Bearer " + issue_session(db, db.get(User, user_id), 3600)}
    path = f"/api/organizations/{org}/microsoft"
    server.root = "https://login.microsoftonline.com/organizations"
    server.subject = str(uuid4())
    original = server.subject
    opened = client.post(path + "/connect", headers=auth, json={"capabilities": ["mail", "files"]})
    assert opened.status_code == 200, opened.text
    callback = server.authorize(opened.json()["authorization_url"])
    assert client.post(CALLBACK, data=callback, follow_redirects=False).status_code == 303
    server.root = f"https://login.microsoftonline.com/{server.tenant}"
    assert (
        client.get(path + "/mail", headers=auth).json()["messages"][0]["subject"]
        == "synthetic-renewed-" + original
    )
    assert client.get(path + "/mail", headers=bob[2]).status_code == 409
    # A reconnect is pinned to the bound Microsoft identity even though login is independent.
    opened = client.post(path + "/connect", headers=auth, json={"capabilities": ["mail", "files"]})
    server.subject = str(uuid4())
    callback = server.authorize(opened.json()["authorization_url"])
    assert client.post(CALLBACK, data=callback, follow_redirects=False).status_code == 403
    assert (
        client.get(path + "/mail", headers=auth).json()["messages"][0]["subject"]
        == "synthetic-renewed-" + original
    )
    assert client.get("/api/me", headers=auth).json()["id"] == user_id
    assert client.delete(path, headers=auth).status_code == 204
    assert client.get(path + "/mail", headers=auth).status_code == 409
