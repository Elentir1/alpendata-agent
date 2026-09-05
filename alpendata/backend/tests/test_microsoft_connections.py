"""Real application, MSAL and SQL transactions; synthetic external HTTP only."""

import base64
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import msal
import pytest
from cryptography.fernet import Fernet, InvalidToken
from fastapi.testclient import TestClient
from requests import Response
from sqlalchemy import select
from test_microsoft_signin import MicrosoftHTTP

from alpendata_api.auth import issue_session
from alpendata_api.connections import context
from alpendata_api.graph import GraphReader
from alpendata_api.microsoft_data import CALLBACK, MicrosoftData
from alpendata_api.models import Membership, MicrosoftConnection, User
from alpendata_api.settings import Settings
from alpendata_api.vault import Vault


class GraphHTTP:
    def __init__(self):
        self.calls = []
        self.status = 200

    def request(self, method, url, **kwargs):
        assert kwargs["allow_redirects"] is False
        assert kwargs["timeout"] == 20
        assert url.startswith("https://graph.microsoft.com/v1.0/")
        self.calls.append((method, url, kwargs))
        token = kwargs["headers"]["Authorization"].removeprefix("Bearer ")
        value = {
            "/me/messages": {
                "value": [{"id": "message", "subject": token, "bodyPreview": "<script>untrusted</script>"}],
                "@odata.nextLink": "https://outside.example.com/steal",
            },
            "/me/calendarView": {"value": [{"id": "meeting", "subject": "Coaching"}]},
            "/search/query": {
                "value": [
                    {
                        "hitsContainers": [
                            {
                                "hits": [
                                    {
                                        "resource": {
                                            "id": "document",
                                            "name": "Plan.docx",
                                            "parentReference": {"driveId": "shared-drive"},
                                            "webUrl": "https://example.sharepoint.com/Plan.docx",
                                            "@microsoft.graph.downloadUrl": "secret-link",
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ]
            },
        }[url.removeprefix("https://graph.microsoft.com/v1.0")]
        response = Response()
        response.status_code = self.status
        response.headers.update({"Location": "https://outside.example.com/steal", "Retry-After": "91"})
        response._content = json.dumps(value).encode()
        response._content_consumed = True
        return response


class DataHTTP(MicrosoftHTTP):
    def __init__(self, *args):
        super().__init__(*args)
        self.refreshes = []
        self.refresh_error = False
        self.exchange_started, self.exchange_release = None, None

    def get(self, url, **kwargs):
        if url == "https://login.microsoftonline.com/common/discovery/instance":
            return self.response(
                {
                    "metadata": [
                        {
                            "preferred_network": "login.microsoftonline.com",
                            "preferred_cache": "login.microsoftonline.com",
                            "aliases": ["login.microsoftonline.com"],
                        }
                    ]
                }
            )
        return super().get(url, **kwargs)

    def post(self, url, data=None, **kwargs):
        if data["grant_type"] == "refresh_token":
            assert url == self.root + "/oauth2/v2.0/token"
            self.refreshes.append(data["refresh_token"])
            if self.refresh_error:
                return self.response({"error": self.refresh_error, "error_description": "Synthetic failure"})
            subject = data["refresh_token"].removeprefix("synthetic-refresh-")
            return self.response(
                {
                    "access_token": "synthetic-renewed-" + subject,
                    "token_type": "Bearer",
                    "scope": data["scope"],
                    "expires_in": 3600,
                    "client_info": base64.urlsafe_b64encode(
                        json.dumps({"uid": subject, "utid": self.tenant}).encode()
                    ).decode(),
                }
            )
        if self.exchange_started is not None:
            self.exchange_started.set()
            assert self.exchange_release.wait(20)
        return super().post(url, data, **kwargs)


@pytest.fixture
def connected_service(database_url, service_factory):
    settings = Settings(
        database_url=database_url,
        public_origin="https://alpendata.example.test",
        microsoft_client_id=str(uuid4()),
        microsoft_client_secret="synthetic",
        credential_keys=(Fernet.generate_key().decode(),),
    )
    server = DataHTTP(
        settings.microsoft_client_id, ("openid", "profile", "offline_access", "Mail.Read", "Files.Read.All")
    )
    graph = GraphHTTP()
    server.root = f"https://login.microsoftonline.com/{server.tenant}"
    provider = MicrosoftData(settings, http_client=server)
    with service_factory(settings, microsoft_provider=provider, graph=GraphReader(graph)) as (app, client):

        def account():
            with app.state.session_factory.begin() as db:
                user = User(
                    issuer=f"https://login.microsoftonline.com/{server.tenant}/v2.0",
                    subject=str(uuid4()),
                    display_name="Coach",
                )
                db.add(user)
                db.flush()
                return user.id, user.subject, {"Authorization": "Bearer " + issue_session(db, user, 3600)}

        alice, bob = account(), account()
        org = client.post("/api/organizations", headers=alice[2], json={"name": "Coaches"}).json()["id"]
        with app.state.session_factory.begin() as db:
            db.add(Membership(organization_id=org, user_id=bob[0], role="member"))
        yield app, client, settings, server, graph, org, alice, bob


def start(client, server, org, account, capabilities=("mail", "files"), overrides=None):
    server.subject = account[1]
    response = client.post(
        f"/api/organizations/{org}/microsoft/connect",
        headers=account[2],
        json={"capabilities": list(capabilities)},
    )
    assert response.status_code == 200, response.text
    assert "HttpOnly" in response.headers["set-cookie"] and "Secure" in response.headers["set-cookie"]
    return server.authorize(response.json()["authorization_url"], overrides)


def test_personal_scopes_encrypted_cache_and_fixed_graph_reads(connected_service):
    app, client, settings, server, graph, org, alice, bob = connected_service
    path = f"/api/organizations/{org}/microsoft"
    for account in (alice, bob):
        flow = start(client, server, org, account)
        assert client.post(CALLBACK, data=flow, follow_redirects=False).status_code == 303
        assert client.post(CALLBACK, data=flow).status_code == 400
    with app.state.session_factory() as db:
        entries = db.scalars(select(MicrosoftConnection)).all()
        assert {entry.owner_id for entry in entries} == {alice[0], bob[0]}
        for entry in entries:
            assert "synthetic-access-" not in entry.encrypted_cache
            assert "synthetic-refresh-" not in entry.encrypted_cache
            with pytest.raises(InvalidToken):
                Vault(settings.credential_keys).open(
                    context(entries[1 - entries.index(entry)]), entry.encrypted_cache
                )
    for account in (alice, bob):
        metadata = client.get(path, headers=account[2]).json()
        assert metadata["status"] == "connected" and set(metadata["capabilities"]) == {"mail", "files"}
        assert "cache" not in json.dumps(metadata) and "token" not in json.dumps(metadata)
        mail = client.get(path + "/mail", headers=account[2])
        assert mail.status_code == 200, mail.text
        assert mail.json()["messages"][0]["subject"] == "synthetic-access-" + account[1]
        before = len(graph.calls)
        assert client.get(path + "/calendar", headers=account[2]).status_code == 403
        assert len(graph.calls) == before
    assert client.post(path + "/files/search", headers=alice[2], json={"query": "coaching"}).json() == {
        "files": [
            {
                "id": "document",
                "name": "Plan.docx",
                "drive_id": "shared-drive",
                "url": "https://example.sharepoint.com/Plan.docx",
                "modified_at": None,
            }
        ]
    }
    assert (
        client.post(
            path + "/connect", headers=alice[2], json={"capabilities": ["mail"], "owner_id": bob[0]}
        ).status_code
        == 422
    )
    assert (
        client.post(
            path + "/files/search",
            headers=alice[2],
            json={"query": "test", "url": "https://outside.example.com"},
        ).status_code
        == 422
    )
    assert client.get(f"/api/organizations/{uuid4()}/microsoft/mail", headers=alice[2]).status_code == 404
    # Graph redirects and next links must never forward credentials to a new host.
    graph.status = 302
    count = len(graph.calls)
    assert client.get(path + "/mail", headers=alice[2]).status_code == 502
    assert len(graph.calls) == count + 1
    graph.status = 429
    limited = client.get(path + "/mail", headers=alice[2])
    assert limited.status_code == 429 and limited.headers["retry-after"] == "91"
    graph.status = 401
    assert client.get(path + "/mail", headers=alice[2]).status_code == 409
    assert client.get(path, headers=alice[2]).json()["status"] == "reconnect_required"
    graph.status = 200
    assert client.get(path + "/mail", headers=bob[2]).status_code == 200
    assert client.delete(path, headers=bob[2]).status_code == 204
    with app.state.session_factory() as db:
        assert all(entry.encrypted_cache is None for entry in db.scalars(select(MicrosoftConnection)))


def test_consent_requires_same_account_browser_and_live_membership(connected_service):
    app, client, settings, server, graph, org, alice, bob = connected_service
    path = f"/api/organizations/{org}/microsoft"
    flow = start(client, server, org, bob)
    with TestClient(app, base_url=settings.public_origin) as other_browser:
        assert other_browser.post(CALLBACK, data=flow).status_code == 400
    assert server.exchanges == 0
    assert client.delete(path, headers=bob[2]).status_code == 204
    assert client.post(CALLBACK, data=flow).status_code == 400
    assert server.exchanges == 0
    wrong_account = start(client, server, org, alice, overrides={"oid": bob[1]})
    assert client.post(CALLBACK, data=wrong_account).status_code == 403
    assert client.get(path, headers=alice[2]).json()["status"] == "disconnected"
    flow = start(client, server, org, bob)
    with app.state.session_factory.begin() as db:
        db.get(Membership, (org, bob[0])).active = False
    before = server.exchanges
    assert client.post(CALLBACK, data=flow).status_code == 404
    assert server.exchanges == before and not graph.calls
    flow = start(client, server, org, alice)
    assert client.post("/api/logout", headers=alice[2]).status_code == 204
    assert client.post(CALLBACK, data=flow).status_code == 401
    assert server.exchanges == before


def remove_access_tokens(app, settings, owner):
    with app.state.session_factory.begin() as db:
        connection = db.scalar(select(MicrosoftConnection).where(MicrosoftConnection.owner_id == owner))
        vault = Vault(settings.credential_keys)
        cache = msal.SerializableTokenCache()
        cache.deserialize(vault.open(context(connection), connection.encrypted_cache)["cache"])
        for token in list(cache.search(msal.TokenCache.CredentialType.ACCESS_TOKEN)):
            cache.remove_at(token)
        connection.encrypted_cache = vault.seal(context(connection), {"cache": cache.serialize()})


def test_refresh_uses_only_owners_cache_and_revocation_is_persisted(connected_service):
    app, client, settings, server, graph, org, alice, bob = connected_service
    path = f"/api/organizations/{org}/microsoft"
    for account in (alice, bob):
        flow = start(client, server, org, account)
        assert client.post(CALLBACK, data=flow, follow_redirects=False).status_code == 303
    remove_access_tokens(app, settings, alice[0])
    result = client.get(path + "/mail", headers=alice[2])
    assert result.status_code == 200, result.text
    assert result.json()["messages"][0]["subject"] == "synthetic-renewed-" + alice[1]
    assert server.refreshes == ["synthetic-refresh-" + alice[1]]
    assert client.get(path + "/mail", headers=alice[2]).status_code == 200
    assert len(server.refreshes) == 1
    remove_access_tokens(app, settings, alice[0])
    server.refresh_error = "temporarily_unavailable"
    assert client.get(path + "/mail", headers=alice[2]).status_code == 502
    assert client.get(path, headers=alice[2]).json()["status"] == "connected"
    server.refresh_error = "invalid_grant"
    before = len(graph.calls)
    assert client.get(path + "/mail", headers=alice[2]).status_code == 409
    assert len(graph.calls) == before
    assert client.get(path, headers=alice[2]).json()["status"] == "reconnect_required"
    assert client.get(path + "/mail", headers=bob[2]).status_code == 200


@pytest.mark.linux_only
def test_disconnect_during_exchange_cannot_resurrect_credentials(connected_service):
    app, client, settings, server, graph, org, alice, bob = connected_service
    flow = start(client, server, org, alice)
    server.exchange_started, server.exchange_release = Event(), Event()
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(client.post, CALLBACK, data=flow, follow_redirects=False)
        try:
            assert server.exchange_started.wait(20)
            assert client.delete(f"/api/organizations/{org}/microsoft", headers=alice[2]).status_code == 204
        finally:
            server.exchange_release.set()
        assert pending.result(timeout=20).status_code == 409
    with app.state.session_factory() as db:
        connection = db.scalar(select(MicrosoftConnection).where(MicrosoftConnection.owner_id == alice[0]))
        assert connection.status == "disconnected" and connection.encrypted_cache is None
