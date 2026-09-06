import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text

pytestmark = pytest.mark.linux_only


def control(*arguments, check=True):
    result = subprocess.run(
        ["systemctl", "--user", *arguments],
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, "XDG_RUNTIME_DIR": f"/run/user/{os.getuid()}"},
    )
    if check:
        assert result.returncode == 0, result.stderr
    return result


def state(name):
    result = control("show", name, "--property=ActiveState,MainPID,ExecMainStatus,NRestarts,Result")
    return dict(line.split("=", 1) for line in result.stdout.splitlines())


def journal(name):
    return subprocess.run(
        ["journalctl", "--user", "-u", name, "--no-pager", "-o", "cat"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout


def wait_for(condition):
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.2)
    raise AssertionError("Temporary systemd service did not reach the expected state")


@pytest.fixture
def managed(service, request):
    if not request.config.getoption("--systemd-user") or not request.config.getoption("--postgresql-bin"):
        pytest.skip("Requires --systemd-user and real PostgreSQL")
    assert sys.platform == "linux"
    control("show", "--property=Version")
    app, _ = service
    with tempfile.TemporaryDirectory(prefix="alpendata-systemd-") as temporary:
        directory = Path(temporary)
        environment = directory / "service configuration.env"
        environment.write_text(
            f"ALPENDATA_DATABASE_URL={app.state.engine.url}\n"
            "ALPENDATA_MODEL_PROVIDER=mistral\nALPENDATA_MODEL_ID=synthetic-model\n"
            "ALPENDATA_MODEL_API_KEY=private-synthetic-unit-key\n"
            f"ALPENDATA_RUNTIME_STATE_ROOT={directory / 'states'}\n"
            f"ALPENDATA_RUNTIME_IMAGE=sha256:{'0' * 64}\n"
            "ALPENDATA_PUBLIC_ORIGIN=https://localhost\nALPENDATA_MICROSOFT_CLIENT_ID=\n"
            "ALPENDATA_MICROSOFT_CLIENT_SECRET=\nALPENDATA_CREDENTIAL_KEYS=\n"
            "ALPENDATA_SMTP_HOST=\nALPENDATA_SMTP_PORT=465\nALPENDATA_SMTP_SENDER=\n"
            "ALPENDATA_SMTP_USERNAME=\nALPENDATA_SMTP_PASSWORD=\nALPENDATA_MODEL_ALLOWED_PROVIDERS=\n"
            "ALPENDATA_STRIPE_API_KEY=rk_"
            "test_syntheticunit\n"
            "ALPENDATA_STRIPE_WEBHOOK_SECRET=whsec_"
            "syntheticunit\n"
            "ALPENDATA_STRIPE_PRICE_ID=price_seats\nALPENDATA_STRIPE_PORTAL_CONFIGURATION_ID=bpc_portal\n"
        )
        environment.chmod(0o600)
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        output = directory / "units"
        working = directory / "working directory"
        working.mkdir()
        generate = [
            sys.executable,
            "-m",
            "alpendata_api.service_units",
            "--python",
            sys.executable,
            "--backend",
            str(working),
            "--environment",
            str(environment),
            "--api-port",
            str(port),
            "--output",
            str(output),
            "--with-billing",
        ]
        subprocess.run(generate, check=True, capture_output=True, timeout=15)
        assert subprocess.run(generate, capture_output=True, timeout=15).returncode != 0
        prefix = "alpendata-test-" + uuid4().hex
        names = {}
        linked = []
        try:
            for name in ("api", "chat", "scheduler", "billing"):
                path = output / f"{prefix}-{name}.service"
                (output / f"alpendata-{name}.service").rename(path)
                control("link", "--runtime", str(path))
                linked.append(path.name)
                names[name] = path.name
            yield app, names, port
        finally:
            if linked:
                control("stop", *linked, check=False)
                control("disable", "--runtime", *linked)
                control("reset-failed", *linked, check=False)


def test_generated_units_serve_restart_after_crash_and_stop_cleanly(managed):
    _, names, port = managed
    control("start", *names.values())
    with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=2) as client:

        def ready():
            try:
                return client.get("/health/ready").status_code == 200
            except httpx.TransportError:
                return False

        wait_for(ready)
        assert client.get("/api/me").status_code == 401
    for name in ("chat", "scheduler", "billing"):
        wait_for(lambda: '"status": "ready"' in journal(names[name]))
    before = state(names["chat"])
    readies = journal(names["chat"]).count('"status": "ready"')
    assert before["ActiveState"] == "active" and int(before["MainPID"]) > 0
    # Crash an idle controller; this exercise never kills a client job or container.
    control("kill", "--kill-whom=main", "--signal=KILL", names["chat"])
    wait_for(
        lambda: (
            state(names["chat"])["ActiveState"] == "active" and int(state(names["chat"])["NRestarts"]) >= 1
        )
    )
    assert state(names["chat"])["MainPID"] != before["MainPID"]
    wait_for(lambda: journal(names["chat"]).count('"status": "ready"') > readies)
    control("stop", *names.values())
    for name in names.values():
        stopped = state(name)
        assert stopped["ActiveState"] == "inactive"
        assert stopped["ExecMainStatus"] == "0"
        assert "private-synthetic-unit-key" not in journal(name)
        assert "syntheticunit" not in journal(name)


def test_incompatible_service_hits_restart_limit_and_can_recover_after_correction(managed):
    app, names, _ = managed
    with app.state.engine.begin() as db:
        version = db.scalar(text("SELECT version_num FROM alembic_version"))
        db.execute(text("UPDATE alembic_version SET version_num = 'incompatible'"))
    name = names["chat"]
    control("start", name)
    wait_for(lambda: state(name)["ActiveState"] == "failed" and int(state(name)["NRestarts"]) >= 3)
    failed = state(name)
    assert failed["ActiveState"] == "failed" and failed["MainPID"] == "0"
    output = journal(name)
    assert output.count('"status": "database_unavailable"') == 3
    assert '"status": "ready"' not in output
    assert "private-synthetic-unit-key" not in output
    with app.state.engine.begin() as db:
        db.execute(text("UPDATE alembic_version SET version_num = :version"), {"version": version})
    control("reset-failed", name)
    control("start", name)
    wait_for(lambda: '"status": "ready"' in journal(name))
    control("stop", name)
    assert state(name)["ExecMainStatus"] == "0"
