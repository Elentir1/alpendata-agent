import ipaddress
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path

import httpx
import pytest
import uvicorn
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from alpendata_api.auth import SESSION_COOKIE, issue_session
from alpendata_api.ingress import nginx_config
from alpendata_api.models import User
from alpendata_api.settings import Settings

pytestmark = pytest.mark.linux_only


class Assets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        field = {"script": "src", "link": "href"}.get(tag)
        if field and attributes.get(field, "").startswith("/"):
            self.urls.append(attributes[field])


def certificate(directory):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "AlpenData test only")])
    at = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(at - timedelta(minutes=1))
        .not_valid_after(at + timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), False
        )
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), True)
        .sign(key, hashes.SHA256())
    )
    cert_path, key_path = directory / "test.pem", directory / "test.key"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
    )
    key_path.chmod(0o600)
    return cert_path, key_path


def wait_http(client, path, process_alive):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline and process_alive():
        try:
            if client.get(path).status_code == 200:
                return
        except httpx.TransportError:
            pass
        time.sleep(0.05)
    raise AssertionError("Local server did not become ready")


@pytest.fixture
def ingress(request, service_factory):
    binary, dist = request.config.getoption("--nginx-bin"), request.config.getoption("--frontend-dist")
    if not binary or not dist:
        pytest.skip("Supply --nginx-bin and --frontend-dist for a real HTTPS exercise")
    assert Path(binary).is_absolute() and Path(binary).is_file()
    assert (Path(dist) / "index.html").is_file()
    with tempfile.TemporaryDirectory(prefix="alpendata-https-") as temporary:
        directory = Path(temporary)
        frontend = directory / "frontend release"
        shutil.copytree(dist, frontend)
        (frontend / ".env").write_text("private-test-sentinel")
        (directory / "outside.png").write_text("private-test-sentinel")
        (frontend / "brand" / "linked.png").symlink_to(directory / "outside.png")
        runtime = directory / "run"
        runtime.mkdir(mode=0o700)
        cert, key = certificate(directory)
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        origin = f"https://127.0.0.1:{port}"
        database_url = request.getfixturevalue("database_url")
        with service_factory(Settings(database_url=database_url, public_origin=origin)) as (app, _):
            with socket.socket() as api_socket:
                api_socket.bind(("127.0.0.1", 0))
                api_port = api_socket.getsockname()[1]
                server = uvicorn.Server(
                    uvicorn.Config(
                        app,
                        access_log=False,
                        log_level="critical",
                        proxy_headers=True,
                        forwarded_allow_ips="127.0.0.1",
                    )
                )
                thread = threading.Thread(target=server.run, kwargs={"sockets": [api_socket]}, daemon=True)
                thread.start()
                process = None
                try:
                    with httpx.Client(base_url=f"http://127.0.0.1:{api_port}", trust_env=False) as direct:
                        wait_http(direct, "/health/ready", thread.is_alive)
                    config = directory / "nginx.conf"
                    generate = [
                        sys.executable,
                        "-m",
                        "alpendata_api.ingress",
                        "--origin",
                        origin,
                        "--frontend",
                        str(frontend),
                        "--certificate",
                        str(cert),
                        "--private-key",
                        str(key),
                        "--run-directory",
                        str(runtime),
                        "--bind",
                        "127.0.0.1",
                        "--api-port",
                        str(api_port),
                        "--output",
                        str(config),
                    ]
                    subprocess.run(generate, check=True, capture_output=True, timeout=15)
                    candidate = config.read_bytes()
                    assert subprocess.run(generate, capture_output=True, timeout=15).returncode != 0
                    assert config.read_bytes() == candidate
                    command = [binary, "-p", str(directory), "-c", str(config), "-e", "stderr"]
                    validation = subprocess.run([*command, "-t"], capture_output=True, timeout=15)
                    assert validation.returncode == 0, validation.stderr.decode()
                    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                    context = ssl.create_default_context(cafile=str(cert))
                    with httpx.Client(base_url=origin, verify=context, trust_env=False) as client:
                        wait_http(client, "/", lambda: process.poll() is None)
                        yield app, client, frontend
                finally:
                    if process is not None:
                        process.terminate()
                        process.communicate(timeout=15)
                    server.should_exit = True
                    thread.join(timeout=20)
                    assert not thread.is_alive()


def test_https_serves_built_assets_without_exposing_internal_files(ingress):
    _, client, frontend = ingress
    response = client.get("/")
    assert response.content == (frontend / "index.html").read_bytes()
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["cache-control"] == "no-store"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert client.get("/join").content == response.content
    parser = Assets()
    parser.feed(response.text)
    assert any(url.endswith(".js") for url in parser.urls)
    assert any(url.endswith(".css") for url in parser.urls)
    for url in [*parser.urls, "/brand/inter-400.woff2", "/brand/inter-700.woff2"]:
        asset = client.get(url)
        assert asset.status_code == 200
        assert asset.content == (frontend / url.removeprefix("/")).read_bytes()
        assert asset.headers["content-type"] != "application/octet-stream"
    for url in (
        "/.env",
        "/assets/missing.js",
        "/assets/index.js.map",
        "/docs",
        "/openapi.json",
        "/health/ready",
        "/brand/linked.png",
        "/missing",
        "/%2eenv",
    ):
        denied = client.get(url)
        assert denied.status_code in {403, 404}
        assert "private-test-sentinel" not in denied.text
    assert client.get("/api/unknown").status_code == 404
    assert client.get("/api/unknown").headers["content-type"].startswith("application/json")
    assert client.get("/", headers={"Host": "foreign.example"}).status_code == 421
    assert client.post("/api/unknown", content=b"x" * (8 * 1024 * 1024 + 1)).status_code == 413
    for changes in (
        {"origin": "https://example.ch:0"},
        {"origin": "https://example.ch:443"},
        {"frontend": "/srv/release\ninclude /etc/private;"},
        {"frontend": "/srv/../private"},
    ):
        values = dict(
            origin="https://example.ch",
            frontend="/srv/frontend",
            certificate="/etc/cert.pem",
            private_key="/etc/key.pem",
            run_directory="/run/alpendata",
        )
        with pytest.raises(ValueError):
            nginx_config(**(values | changes))


def test_proxy_preserves_cookie_authorization_and_exact_origin(ingress):
    app, client, _ = ingress
    assert client.get("/api/me").status_code == 401
    with app.state.session_factory.begin() as db:
        user = User(
            issuer="https://test.example",
            subject="coach",
            verified_email="coach@example.com",
            display_name="Coach HTTPS",
        )
        db.add(user)
        db.flush()
        token = issue_session(db, user, 3600)
        user_id = user.id
    client.cookies.set(SESSION_COOKIE, token, domain="127.0.0.1", path="/")
    assert client.get("/api/me").json()["id"] == user_id
    for origin in (None, "https://foreign.example"):
        response = client.post(
            "/api/organizations", json={"name": "Coaches"}, headers={"Origin": origin} if origin else {}
        )
        assert response.status_code == 403
    origin = str(client.base_url).rstrip("/")
    created = client.post("/api/organizations", json={"name": "Coaches"}, headers={"Origin": origin})
    assert created.status_code == 201
    assert created.headers["cache-control"] == "no-store"
    redirect = client.get(
        "/api/me/",
        headers={
            "X-Forwarded-Proto": "http",
            "X-Forwarded-Host": "foreign.example",
            "Forwarded": "host=foreign.example;proto=http",
            "X-Forwarded-For": "203.0.113.1",
        },
    )
    assert redirect.status_code == 307
    assert redirect.headers["location"] == origin + "/api/me"
    assert client.post("/api/logout", headers={"Origin": origin}).status_code == 204
    assert client.get("/api/me").status_code == 401
