import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from alpendata_api.app import create_app
from alpendata_api.auth import issue_session
from alpendata_api.models import User
from alpendata_api.settings import Settings


def pytest_addoption(parser):
    parser.addoption(
        "--postgresql-bin", help="PostgreSQL bin directory for disposable Unix-socket test servers"
    )


def pytest_collection_modifyitems(items):
    if sys.platform != "linux":
        for item in items:
            if "linux_only" in item.keywords:
                item.add_marker(pytest.mark.skip(reason="Requires a real Linux host"))


@pytest.fixture
def database_url(tmp_path, request):
    binaries = request.config.getoption("--postgresql-bin")
    if not binaries:
        yield f"sqlite:///{tmp_path / 'alpendata.db'}"
        return
    binaries = Path(binaries)
    # Short socket paths avoid the Unix socket name limit. No TCP listener is opened.
    with tempfile.TemporaryDirectory(prefix="alpendata-pg-") as temporary:
        directory = Path(temporary).resolve()
        data, sockets = directory / "data", directory / "socket"
        sockets.mkdir(mode=0o700)
        subprocess.run(
            [
                str(binaries / "initdb"),
                "-D",
                str(data),
                "-U",
                "alpendata_test",
                "--auth=trust",
                "--no-locale",
                "--encoding=UTF8",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        subprocess.run(
            [
                str(binaries / "pg_ctl"),
                "-D",
                str(data),
                "-l",
                str(directory / "server.log"),
                "-o",
                f"-c listen_addresses= -c unix_socket_directories={sockets}",
                "-w",
                "start",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        try:
            yield f"postgresql+psycopg://alpendata_test@/postgres?host={sockets}"
        finally:
            subprocess.run(
                [
                    str(binaries / "pg_ctl"),
                    "-D",
                    str(data),
                    "-m",
                    "fast",
                    "-w",
                    "stop",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )


@pytest.fixture
def mail_outbox():
    return []


@pytest.fixture
def service_factory(database_url, mail_outbox):
    class RecordingMailer:
        def send(self, message):
            mail_outbox.append(message)

    @contextmanager
    def build(settings=None, provider=None, mailer=None):
        settings = settings or Settings(
            database_url=database_url,
            smtp_sender="noreply@example.com",
            smtp_host="smtp.example.test",
            smtp_username="synthetic",
            smtp_password="synthetic",
        )
        app = create_app(settings, signin_provider=provider, mailer=mailer or RecordingMailer())
        configuration = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        with app.state.engine.begin() as connection:
            configuration.attributes["connection"] = connection
            command.upgrade(configuration, "head")
            command.check(configuration)
        with TestClient(app, base_url=settings.public_origin) as client:
            yield app, client

    return build


@pytest.fixture
def service(service_factory):
    with service_factory() as pair:
        yield pair


@pytest.fixture
def account(service):
    app, _ = service

    def create(email):
        with app.state.session_factory.begin() as db:
            user = User(
                issuer="https://identity.example.test",
                subject=email,
                verified_email=email,
                display_name=email.split("@")[0],
            )
            db.add(user)
            db.flush()
            token = issue_session(db, user, 3600)
            return user.id, {"Authorization": f"Bearer {token}"}

    return create


@pytest.fixture
def verification(service, mail_outbox):
    _, client = service

    def request(headers, invitation):
        response = client.post("/api/invitations/verify", headers=headers, json={"token": invitation})
        assert response.status_code == 202
        assert "verification_token" not in response.json()
        link = next(
            line for line in mail_outbox[-1].get_content().splitlines() if line.startswith("https://")
        )
        values = parse_qs(urlsplit(link).fragment)
        assert values["invitation"] == [invitation]
        return values["verification"][0]

    return request
