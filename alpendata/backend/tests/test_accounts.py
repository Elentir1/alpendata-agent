import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient
from sqlalchemy import select

from alpendata_api.accounts import provision
from alpendata_api.backup_restore import suspend_restored_work
from alpendata_api.models import PasswordAccount
from alpendata_api.settings import Settings

PASSWORD = "A private long passphrase for QA 42!"


def test_operator_cli_provisions_members_with_capacity_and_never_outputs_activation_secret(
    service_factory, database_url, tmp_path
):
    with service_factory(Settings(database_url=database_url)) as (app, client):
        environment = {key: value for key, value in os.environ.items() if not key.startswith("ALPENDATA_")}
        environment["ALPENDATA_DATABASE_URL"] = database_url
        destination = tmp_path / "activation.txt"
        command = [
            sys.executable,
            "-m",
            "alpendata_api.accounts",
            "create",
            "--email",
            "owner@example.com",
            "--name",
            "Owner",
            "--activation-file",
            str(destination),
        ]
        result = subprocess.run(command, env=environment, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stdout
        token = parse_qs(urlsplit(destination.read_text().strip()).fragment)["activation"][0]
        assert token not in result.stdout + result.stderr
        assert json.loads(result.stdout)["status"] == "activation_prepared"
        if os.name != "nt":
            assert destination.stat().st_mode & 0o777 == 0o600
        assert (
            client.post(
                "/api/auth/password/activate",
                headers={"Origin": "https://localhost"},
                json={"token": token, "password": PASSWORD},
            ).status_code
            == 204
        )
        company = client.post(
            "/api/organizations", headers={"Origin": "https://localhost"}, json={"name": "Pilot"}
        ).json()["id"]
        with app.state.session_factory.begin() as db:
            for email in ("two@example.com", "three@example.com"):
                provision(db, email, "Colleague", organization_id=company)
        command[command.index("owner@example.com")] = "four@example.com"
        command[command.index(str(destination))] = str(tmp_path / "four.txt")
        result = subprocess.run(
            command + ["--organization-id", company],
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 1 and "account_operation_failed" in result.stdout
        with app.state.session_factory() as db:
            assert (
                db.scalar(select(PasswordAccount).where(PasswordAccount.email == "four@example.com")) is None
            )
        # Exclusive output refuses replacement, including an existing activation file.
        result = subprocess.run(
            command[: command.index("--activation-file") + 1] + [str(destination)],
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 1 and token in destination.read_text()


def test_concurrent_activation_has_one_winner_and_restoration_disables_old_passwords(
    service_factory, database_url
):
    settings = Settings(database_url=database_url)
    with service_factory(settings) as (app, client):
        with app.state.session_factory.begin() as db:
            account, token = provision(db, "owner@example.com", "Owner")
            user_id = account.user_id
        barrier = Barrier(2)

        def activate():
            other = TestClient(app, base_url=settings.public_origin)
            try:
                barrier.wait(timeout=10)
                return other.post(
                    "/api/auth/password/activate",
                    headers={"Origin": settings.public_origin},
                    json={"token": token, "password": PASSWORD},
                ).status_code
            finally:
                other.close()

        with ThreadPoolExecutor(2) as pool:
            assert sorted(pool.map(lambda _: activate(), range(2))) == [204, 400]
        assert (
            client.post(
                "/api/auth/password/login",
                headers={"Origin": settings.public_origin},
                json={"email": "owner@example.com", "password": PASSWORD},
            ).status_code
            == 204
        )
        suspend_restored_work(app.state.session_factory)
        assert client.get("/api/me").status_code == 401
        with app.state.session_factory() as db:
            account = db.get(PasswordAccount, user_id)
            assert account.password_hash is None and account.activation_hash is None
        assert (
            client.post(
                "/api/auth/password/login",
                headers={"Origin": settings.public_origin},
                json={"email": "owner@example.com", "password": PASSWORD},
            ).status_code
            == 401
        )
