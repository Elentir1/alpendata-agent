import multiprocessing
import os
import selectors
import signal
import subprocess
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from threading import Event
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
import requests
from model_http import completion, model_http
from requests.adapters import HTTPAdapter
from sqlalchemy import text
from test_chat import service as service

from alpendata_api.chat_worker import ChatWorker
from alpendata_api.database import database_factory
from alpendata_api.model_gateway import ModelGateway
from alpendata_api.runtime import RuntimeSettings
from alpendata_api.worker_service import run_loop

pytestmark = pytest.mark.linux_only


def child_chat(settings, origin):
    class LocalProvider(HTTPAdapter):
        def send(self, request, **kwargs):
            local = request.copy()
            local.url = origin + urlsplit(request.url).path
            return super().send(local, **kwargs)

    engine, factory = database_factory(settings.database_url)
    try:
        with requests.Session() as session:
            session.mount("https://", LocalProvider())
            worker = ChatWorker(settings, factory, gateway=ModelGateway(settings.model, session=session))
            raise SystemExit(
                run_loop(engine, worker.run_once, service="chat", interval=1, delay_when_idle=True)
            )
    finally:
        engine.dispose()


def test_sigterm_finishes_real_hermes_turn_and_leaves_next_job_queued(service, account, request):
    image = request.config.getoption("--runtime-image")
    if not image or not request.config.getoption("--postgresql-bin"):
        pytest.skip("Requires real OCI image and PostgreSQL")
    app, client = service
    entered, release = Event(), Event()

    def respond(body):
        if body.get("tools"):
            entered.set()
            assert release.wait(45)
        return 200, completion(body, content="Completed before maintenance"), {}

    def queue(email):
        _, headers = account(email)
        org = client.post("/api/organizations", headers=headers, json={"name": "Coaches"}).json()["id"]
        base = f"/api/organizations/{org}"
        assert (
            client.put(
                base + "/onboarding",
                headers=headers,
                json={"language": "en", "role": "Coach", "needs": "Prepare meetings"},
            ).status_code
            == 200
        )
        conversation = client.post(base + "/chat/conversations", headers=headers, json={"language": "en"})
        path = base + "/chat/conversations/" + conversation.json()["id"]
        turn = client.post(
            path + "/turns",
            headers=headers,
            json={"request_id": str(uuid4()), "message": "Prepare my meeting"},
        )
        assert turn.status_code == 202
        return path, headers

    with (
        tempfile.TemporaryDirectory(prefix="alpendata-drain-") as temporary,
        model_http(respond) as (
            transport,
            received,
            _,
        ),
    ):
        settings = replace(app.state.chat_settings, runtime=RuntimeSettings(Path(temporary), image))
        first, first_headers = queue("first@example.com")
        process = multiprocessing.get_context("spawn").Process(
            target=child_chat, args=(settings, transport.get_adapter("https://").local_origin)
        )
        process.start()
        try:
            assert entered.wait(45)
            second, second_headers = queue("second@example.com")
            os.kill(process.pid, signal.SIGTERM)
            release.set()
            process.join(timeout=45)
            assert process.exitcode == 0
            finished = client.get(first, headers=first_headers).json()["turns"][-1]
            assert finished["status"] == "completed"
            assert finished["response"] == "Completed before maintenance"
            pending = client.get(second, headers=second_headers).json()["turns"][-1]
            assert pending["status"] == "queued"
            assert sum(bool(call["body"].get("tools")) for call in received) == 1
        finally:
            release.set()
            process.join(timeout=45)
            if process.is_alive():
                process.kill()
                process.join(timeout=10)


def test_worker_commands_stop_idle_and_refuse_wrong_schema_without_logging_secrets(service):
    app, _ = service
    environment = {key: value for key, value in os.environ.items() if not key.startswith("ALPENDATA_")}
    environment.update(
        {
            "ALPENDATA_DATABASE_URL": str(app.state.engine.url),
            "ALPENDATA_MODEL_PROVIDER": "mistral",
            "ALPENDATA_MODEL_ID": "synthetic-model",
            "ALPENDATA_MODEL_API_KEY": "private-synthetic-service-key",
            "ALPENDATA_RUNTIME_STATE_ROOT": str(app.state.chat_settings.runtime.state_root),
            "ALPENDATA_RUNTIME_IMAGE": "sha256:" + "0" * 64,
        }
    )
    billing_environment = {
        key: value
        for key, value in environment.items()
        if not key.startswith(("ALPENDATA_MODEL_", "ALPENDATA_RUNTIME_"))
    }
    billing_environment.update(
        {
            "ALPENDATA_STRIPE_API_KEY": "rk_" + "test_syntheticprocess",
            "ALPENDATA_STRIPE_WEBHOOK_SECRET": "whsec_" + "syntheticprocess",
            "ALPENDATA_STRIPE_PRICE_ID": "price_seats",
            "ALPENDATA_STRIPE_PORTAL_CONFIGURATION_ID": "bpc_portal",
        }
    )
    environments = {"chat": environment, "schedule": environment, "billing": billing_environment}
    for name, process_environment in environments.items():
        command = [sys.executable, "-m", f"alpendata_api.{name}_worker"]
        process = subprocess.Popen(
            command, env=process_environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                assert selector.select(timeout=20), "Worker did not announce startup"
                ready = process.stdout.readline()
                assert b'"status": "ready"' in ready, ready
            process.send_signal(signal.SIGTERM if name == "chat" else signal.SIGINT)
            stdout, stderr = process.communicate(timeout=10)
            assert process.returncode == 0
            assert b'"status": "stopped"' in stdout
            assert b"private-synthetic-service-key" not in stdout + stderr
            assert b"syntheticprocess" not in stdout + stderr
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=10)
    with app.state.engine.begin() as db:
        db.execute(text("UPDATE alembic_version SET version_num = 'wrong-version'"))
    for name, process_environment in environments.items():
        result = subprocess.run(
            [sys.executable, "-m", f"alpendata_api.{name}_worker"],
            env=process_environment,
            capture_output=True,
            timeout=20,
        )
        assert result.returncode == 1
        assert b'"status": "database_unavailable"' in result.stdout
        assert not result.stderr
        assert b"private-synthetic-service-key" not in result.stdout
