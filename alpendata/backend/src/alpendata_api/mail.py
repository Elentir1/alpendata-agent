"""Product transactional mail, separate from any collaborator's mail connection."""

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from urllib.parse import urlencode

from .schemas import InviteInput
from .settings import Settings


def invitation_message(settings: Settings, recipient: str, invitation: str, proof: str, language: str):
    sender = InviteInput(email=settings.smtp_sender).email
    recipient = InviteInput(email=recipient).email
    # Fragments are read by the frontend and POSTed. They are not sent in URLs to
    # the web server, proxy logs or HTTP Referrer headers.
    link = settings.public_origin + "/join#" + urlencode({"invitation": invitation, "verification": proof})
    titles = {"fr": "Confirmez votre invitation AlpenData", "en": "Confirm your AlpenData invitation"}
    bodies = {
        "fr": (
            "Pour rejoindre votre entreprise sur AlpenData, ouvrez ce lien avec le compte qui a demandé "
            "cette vérification :\n\n{link}\n\nCe lien est valable 15 minutes et utilisable une seule fois. "
            "Si vous n’avez pas demandé cette vérification, ignorez ce message.\n\nAlpenData"
        ),
        "en": (
            "To join your company on AlpenData, open this link with the account that requested "
            "this verification:\n\n{link}\n\nThis link expires in 15 minutes and can only be used once. "
            "If you did not request this verification, ignore this message.\n\nAlpenData"
        ),
    }
    message = EmailMessage()
    message["From"], message["To"] = sender, recipient
    message["Subject"] = titles[language]
    message["Date"] = formatdate(localtime=False)
    message["Message-ID"] = make_msgid(domain=sender.rsplit("@", 1)[1])
    message.set_content(bodies[language].format(link=link))
    return message


class SMTPMailer:
    def __init__(self, settings: Settings, *, tls_context: ssl.SSLContext | None = None):
        self.settings = settings
        self.tls = tls_context or ssl.create_default_context()
        if not self.tls.check_hostname or self.tls.verify_mode != ssl.CERT_REQUIRED:
            raise ValueError("SMTP requires certificate and hostname validation")

    def send(self, message: EmailMessage):
        if not self.settings.smtp_enabled:
            raise RuntimeError("Transactional mail is not configured")
        # TLS from the first byte. Never retry an uncertain DATA outcome here.
        with smtplib.SMTP_SSL(
            self.settings.smtp_host,
            self.settings.smtp_port,
            timeout=15,
            context=self.tls,
            local_hostname="alpendata",
        ) as connection:
            connection.login(self.settings.smtp_username, self.settings.smtp_password)
            connection.send_message(message)
