"""Real MSAL exchange with an in-memory Microsoft HTTP contract; no external accounts."""

import base64
import hashlib
import json
import secrets
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import jwt
import pytest
from cryptography.fernet import Fernet, InvalidToken
from fastapi.testclient import TestClient
from requests import Response
from sqlalchemy import select

from alpendata_api.auth import BROWSER_COOKIE, SESSION_COOKIE, token_digest
from alpendata_api.microsoft_identity import MicrosoftSignIn
from alpendata_api.models import AuthSession, SignInFlow, User, now
from alpendata_api.settings import Settings
from alpendata_api.vault import Vault


class MicrosoftHTTP:
    """Only the two documented Microsoft endpoints can be reached by this fixture."""

    root = "https://login.microsoftonline.com/organizations"

    def __init__(self, client_id):
        self.client_id = client_id
        self.tenant, self.subject = str(uuid4()), str(uuid4())
        self.codes = {}
        self.exchanges = 0

    def response(self, value):
        response = Response()
        response.status_code = 200
        response._content = json.dumps(value).encode()
        response.headers["Content-Type"] = "application/json"
        return response

    def get(self, url, **kwargs):
        assert url == self.root + "/v2.0/.well-known/openid-configuration"
        return self.response(
            {
                "authorization_endpoint": self.root + "/oauth2/v2.0/authorize",
                "token_endpoint": self.root + "/oauth2/v2.0/token",
                "issuer": "https://login.microsoftonline.com/{tenantid}/v2.0",
            }
        )

    def authorize(self, uri, overrides=None):
        parsed = urlsplit(uri)
        assert parsed.scheme + "://" + parsed.netloc + parsed.path == self.root + "/oauth2/v2.0/authorize"
        query = {key: values[0] for key, values in parse_qs(parsed.query).items()}
        assert query["client_id"] == self.client_id
        assert query["code_challenge_method"] == "S256"
        assert set(query["scope"].split()) == {"openid", "profile"}
        code = secrets.token_urlsafe(32)
        self.codes[code] = query, overrides or {}
        return {"state": query["state"], "code": code}

    def post(self, url, data=None, **kwargs):
        assert url == self.root + "/oauth2/v2.0/token"
        query, overrides = self.codes.pop(data["code"])
        challenge = base64.urlsafe_b64encode(hashlib.sha256(data["code_verifier"].encode()).digest()).rstrip(
            b"="
        )
        assert challenge.decode() == query["code_challenge"]
        assert data["redirect_uri"] == query["redirect_uri"]
        assert data["grant_type"] == "authorization_code"
        self.exchanges += 1
        claims = {
            "iss": f"https://login.microsoftonline.com/{self.tenant}/v2.0",
            "tid": self.tenant,
            "oid": self.subject,
            "sub": "pairwise-subject",
            "aud": self.client_id,
            "exp": now() + 3600,
            "iat": now(),
            "nonce": query["nonce"],
            "name": "Synthetic coach",
            "preferred_username": "coach@example.test",
            "email": "coach@example.test",
            **overrides,
        }
        # MSAL trusts tokens received directly from its TLS token endpoint; this
        # synthetic transport replaces that endpoint, not MSAL or the application.
        return self.response(
            {
                "access_token": "synthetic-unused-access-token",
                "token_type": "Bearer",
                "expires_in": 3600,
                "scope": query["scope"],
                "id_token": jwt.encode(
                    claims, "synthetic-test-key-with-at-least-thirty-two-bytes", algorithm="HS256"
                ),
            }
        )


@pytest.fixture
def signin_service(database_url, service_factory):
    settings = Settings(
        database_url=database_url,
        public_origin="https://alpendata.example.test",
        microsoft_client_id=str(uuid4()),
        microsoft_client_secret="synthetic-client-secret",
        credential_keys=(Fernet.generate_key().decode(),),
    )
    server = MicrosoftHTTP(settings.microsoft_client_id)
    with service_factory(settings, MicrosoftSignIn(settings, http_client=server)) as (app, client):
        yield app, client, settings, server


def begin(client, settings, server, overrides=None):
    response = client.post("/api/auth/microsoft/start", headers={"Origin": settings.public_origin})
    assert response.status_code == 200
    assert "HttpOnly" in response.headers["set-cookie"] and "Secure" in response.headers["set-cookie"]
    return server.authorize(response.json()["authorization_url"], overrides)


def test_signin_is_browser_bound_single_use_and_cookies_require_origin(signin_service):
    app, client, settings, server = signin_service
    assert client.post("/api/auth/microsoft/start").status_code == 403
    callback = begin(client, settings, server)
    with app.state.session_factory() as db:
        pending = db.get(SignInFlow, token_digest(callback["state"]))
        assert callback["state"] not in pending.encrypted_flow
        assert client.cookies.get(BROWSER_COOKIE) not in pending.browser_hash
        with pytest.raises(InvalidToken):
            Vault(settings.credential_keys).open("signin:another-flow", pending.encrypted_flow)
    with TestClient(app, base_url=settings.public_origin) as other_browser:
        assert other_browser.post("/api/auth/microsoft/callback", data=callback).status_code == 400
    response = client.post("/api/auth/microsoft/callback", data=callback, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == settings.public_origin + "/"
    session = client.cookies.get(SESSION_COOKIE)
    assert session and session not in response.text
    assert client.post("/api/auth/microsoft/callback", data=callback).status_code == 400
    assert server.exchanges == 1
    user_id = client.get("/api/me").json()["id"]
    with app.state.session_factory() as db:
        assert (
            db.get(User, user_id).verified_email is None
        )  # Microsoft email is not a proof of mailbox ownership.
        assert db.get(AuthSession, token_digest(session)).user_id == user_id
    assert client.post("/api/organizations", json={"name": "Coaches"}).status_code == 403
    assert (
        client.post(
            "/api/organizations",
            headers={"Origin": "https://attacker.example.test"},
            json={"name": "Coaches"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/organizations", headers={"Origin": settings.public_origin}, json={"name": "Coaches"}
        ).status_code
        == 201
    )
    assert client.post("/api/logout", headers={"Origin": settings.public_origin}).status_code == 204
    assert client.get("/api/me").status_code == 401
    assert client.get("/api/me", headers={"Authorization": f"Bearer {session}"}).status_code == 401


def test_identity_uses_tenant_and_object_id_and_never_merges_matching_emails(signin_service):
    app, client, settings, server = signin_service
    first = begin(client, settings, server)
    assert client.post("/api/auth/microsoft/callback", data=first, follow_redirects=False).status_code == 303
    user_id = client.get("/api/me").json()["id"]
    old_session = client.cookies.get(SESSION_COOKIE)
    second = begin(client, settings, server, {"email": "changed@example.test", "name": "New name"})
    assert client.post("/api/auth/microsoft/callback", data=second, follow_redirects=False).status_code == 303
    assert client.get("/api/me").json()["id"] == user_id
    assert client.get("/api/me", headers={"Authorization": f"Bearer {old_session}"}).status_code == 401
    # An identical address in another directory must create a different identity.
    server.tenant = str(uuid4())
    third = begin(client, settings, server)
    assert client.post("/api/auth/microsoft/callback", data=third, follow_redirects=False).status_code == 303
    assert client.get("/api/me").json()["id"] != user_id
    with app.state.session_factory() as db:
        assert len(db.scalars(select(User)).all()) == 2


@pytest.mark.parametrize(
    "overrides",
    [
        {"nonce": "wrong"},
        {"aud": "wrong"},
        {"iss": "https://attacker.example.test"},
        {"exp": 1},
    ],
)
def test_invalid_provider_identity_never_creates_a_session(signin_service, overrides, caplog):
    app, client, settings, server = signin_service
    callback = begin(client, settings, server, overrides)
    assert (
        client.post("/api/auth/microsoft/callback", data=callback, follow_redirects=False).status_code == 401
    )
    assert client.cookies.get(SESSION_COOKIE) is None
    assert "coach@example.test" not in caplog.text
    assert "Synthetic coach" not in caplog.text
    with app.state.session_factory() as db:
        assert db.scalars(select(User)).all() == []
        assert db.scalars(select(AuthSession)).all() == []
        assert db.get(SignInFlow, token_digest(callback["state"])) is None
