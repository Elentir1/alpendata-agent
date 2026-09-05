import ipaddress
import socket
import ssl
from datetime import datetime, timedelta, timezone
from email import policy
from email.parser import BytesParser

import pytest
from aiosmtpd.controller import Controller
from aiosmtpd.smtp import AuthResult, LoginPassword
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from alpendata_api.mail import SMTPMailer, invitation_message
from alpendata_api.settings import Settings


def test_delivery_uses_authenticated_tls_and_rejects_an_untrusted_certificate(tmp_path):
    # A real SMTP server accepts test messages only on loopback; nothing is relayed.
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "AlpenData SMTP test")])
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc) - timedelta(minutes=1))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(hours=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False
        )
        .sign(private_key, hashes.SHA256())
    )
    cert_path, key_path = tmp_path / "smtp-cert.pem", tmp_path / "smtp-key.pem"
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        private_key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
    )
    server_tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_tls.load_cert_chain(cert_path, key_path)
    client_tls = ssl.create_default_context(cafile=str(cert_path))

    class Inbox:
        messages = []

        async def handle_DATA(self, server, session, envelope):
            assert server.transport.get_extra_info("ssl_object") is not None
            assert session.authenticated
            self.messages.append((envelope.mail_from, envelope.rcpt_tos, envelope.content))
            return "250 Message accepted"

    inbox = Inbox()

    def authenticate(server, session, envelope, mechanism, credentials):
        valid = (
            isinstance(credentials, LoginPassword)
            and credentials.login == b"test-user"
            and credentials.password == b"test-password"
        )
        return AuthResult(success=valid, handled=False)

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    controller = Controller(
        inbox,
        hostname="127.0.0.1",
        port=port,
        ssl_context=server_tls,
        auth_required=True,
        auth_require_tls=False,
        authenticator=authenticate,
    )
    controller.start()
    try:
        settings = Settings(
            database_url="sqlite://",
            public_origin="https://alpendata.example.test",
            smtp_host="127.0.0.1",
            smtp_port=port,
            smtp_sender="noreply@example.com",
            smtp_username="test-user",
            smtp_password="test-password",
        )
        mailer = SMTPMailer(settings, tls_context=client_tls)
        for language in ("fr", "en"):
            message = invitation_message(
                settings, "coach@example.com", "synthetic-invitation", "synthetic-proof", language
            )
            mailer.send(message)
        assert len(inbox.messages) == 2
        for sender, recipients, raw in inbox.messages:
            assert sender == "noreply@example.com" and recipients == ["coach@example.com"]
            parsed = BytesParser(policy=policy.default).parsebytes(raw)
            assert (
                "/join#invitation=synthetic-invitation&verification=synthetic-proof" in parsed.get_content()
            )
        with pytest.raises(ssl.SSLCertVerificationError):
            SMTPMailer(settings).send(message)
        assert len(inbox.messages) == 2
    finally:
        controller.stop()
