from dataclasses import replace

from sqlalchemy import select

from alpendata_api.accounts import provision, reset
from alpendata_api.auth import SESSION_COOKIE
from alpendata_api.models import PasswordAccount, User

PASSWORD = "My long private passphrase 42!"
ORIGIN = {"Origin": "https://localhost"}


def test_manual_accounts_activate_without_microsoft_or_smtp_and_never_merge_identity(
    service_factory, database_url
):
    from alpendata_api.settings import Settings

    with service_factory(Settings(database_url=database_url)) as (app, client):
        with app.state.session_factory.begin() as db:
            db.add(
                User(
                    issuer="microsoft",
                    subject="external",
                    display_name="Existing",
                    verified_email="coach@example.com",
                )
            )
            account, token = provision(db, "Coach@EXAMPLE.com", "Coach")
            user_id = account.user_id
        assert client.get("/api/auth/options").json()["password"] is True
        url = "/api/auth/password/activate"
        payload = {"token": token, "password": PASSWORD}
        assert client.post(url, json=payload).status_code == 403
        assert client.post(url, headers=ORIGIN, json={**payload, "password": "short"}).status_code == 422
        activated = client.post(url, headers=ORIGIN, json=payload)
        assert activated.status_code == 204
        assert "Secure" in activated.headers["set-cookie"] and "HttpOnly" in activated.headers["set-cookie"]
        assert client.get("/api/me").json()["id"] == user_id
        old_session = client.cookies.get(SESSION_COOKIE)
        assert client.post(url, headers=ORIGIN, json=payload).status_code == 400
        company = client.post("/api/organizations", headers=ORIGIN, json={"name": "Independent"})
        assert company.status_code == 201
        assert (
            client.put(
                f"/api/organizations/{company.json()['id']}/onboarding",
                headers=ORIGIN,
                json={"language": "fr", "role": "Coach", "needs": "Préparer mes ateliers"},
            ).status_code
            == 200
        )
        changed = client.post(
            "/api/auth/password/change",
            headers=ORIGIN,
            json={"current_password": PASSWORD, "password": PASSWORD + " new"},
        )
        assert changed.status_code == 204
        assert client.get("/api/me", headers={"Authorization": "Bearer " + old_session}).status_code == 401
        with app.state.session_factory.begin() as db:
            stored = db.get(PasswordAccount, user_id)
            assert stored.password_hash.startswith("$argon2id$") and PASSWORD not in stored.password_hash
            assert stored.activation_hash is None
            assert db.get(User, user_id).verified_email is None
            _, reset_token = reset(db, "coach@example.com")
        assert client.get("/api/me").status_code == 401
        login = "/api/auth/password/login"
        assert (
            client.post(
                login, headers=ORIGIN, json={"email": "coach@example.com", "password": PASSWORD + " new"}
            ).status_code
            == 401
        )
        assert (
            client.post(url, headers=ORIGIN, json={"token": reset_token, "password": PASSWORD}).status_code
            == 204
        )
        assert client.post("/api/logout", headers=ORIGIN).status_code == 204
        assert (
            client.post(
                login, headers=ORIGIN, json={"email": "COACH@example.com", "password": PASSWORD}
            ).status_code
            == 204
        )
        with app.state.session_factory.begin() as db:
            db.get(User, user_id).active = False
        assert client.post(
            login, headers=ORIGIN, json={"email": "coach@example.com", "password": PASSWORD}
        ).json() == {"detail": "invalid_credentials"}


def test_failed_logins_are_generic_throttled_durably_and_secrets_are_not_validation_output(
    service_factory, database_url
):
    from alpendata_api.settings import Settings

    settings = Settings(database_url=database_url)
    with service_factory(settings) as (app, client):
        with app.state.session_factory.begin() as db:
            _, token = provision(db, "person@example.com", "Person")
        path = "/api/auth/password/login"
        missing = {"email": "missing@example.com", "password": PASSWORD}
        assert client.post(path, headers=ORIGIN, json=missing).json() == {"detail": "invalid_credentials"}
        bad = client.post(path, headers=ORIGIN, json={**missing, "password": PASSWORD * 30})
        assert bad.status_code == 422 and PASSWORD not in bad.text
        for _ in range(10):
            response = client.post(path, headers=ORIGIN, json={**missing, "email": "person@example.com"})
            assert response.status_code == 401
    with service_factory(replace(settings)) as (app, client):
        response = client.post(path, headers=ORIGIN, json={**missing, "email": "person@example.com"})
        assert response.status_code == 429 and 1 <= int(response.headers["retry-after"]) <= 300
        with app.state.session_factory.begin() as db:
            account = db.scalar(select(PasswordAccount).where(PasswordAccount.email == "person@example.com"))
            account.activation_expires_at = 1
        assert (
            client.post(
                "/api/auth/password/activate", headers=ORIGIN, json={"token": token, "password": PASSWORD}
            ).status_code
            == 400
        )
