import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from .model_gateway import ModelSettings
from .runtime import RuntimeSettings


@dataclass(frozen=True)
class Settings:
    database_url: str
    session_lifetime_seconds: int = 60 * 60 * 12
    invitation_lifetime_seconds: int = 60 * 60 * 24 * 7
    pilot_seats: int = 3
    public_origin: str = "https://localhost"
    microsoft_client_id: str = ""
    microsoft_client_secret: str = field(default="", repr=False)
    credential_keys: tuple[str, ...] = field(default=(), repr=False)
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_sender: str = ""
    smtp_username: str = field(default="", repr=False)
    smtp_password: str = field(default="", repr=False)
    model: ModelSettings | None = None
    runtime: RuntimeSettings | None = None

    def __post_init__(self):
        if not self.database_url:
            raise ValueError("A database URL is required")
        if min(self.session_lifetime_seconds, self.invitation_lifetime_seconds, self.pilot_seats) < 1:
            raise ValueError("Lifetimes and seat capacity must be positive")
        origin = urlsplit(self.public_origin)
        if (
            origin.scheme != "https"
            or not origin.hostname
            or origin.username
            or origin.password
            or origin.path
            or origin.query
            or origin.fragment
            or origin.netloc != origin.netloc.lower()
        ):
            raise ValueError("Public origin must be an HTTPS origin without a path")
        configured = (
            bool(self.microsoft_client_id),
            bool(self.microsoft_client_secret),
            bool(self.credential_keys),
        )
        if any(configured) and not all(configured):
            raise ValueError("Microsoft sign-in requires client ID, client credential and encryption keys")
        mail = (
            bool(self.smtp_host),
            bool(self.smtp_sender),
            bool(self.smtp_username),
            bool(self.smtp_password),
        )
        if any(mail) and not all(mail):
            raise ValueError("Transactional mail requires SMTP host, sender and credentials")
        if not 1 <= self.smtp_port <= 65535:
            raise ValueError("Invalid SMTP port")
        if bool(self.model) != bool(self.runtime):
            raise ValueError("Chat requires both model and runtime settings")

    @property
    def chat_enabled(self) -> bool:
        return self.model is not None and self.runtime is not None

    @property
    def smtp_enabled(self) -> bool:
        return bool(self.smtp_host and self.smtp_sender and self.smtp_username and self.smtp_password)

    @property
    def microsoft_enabled(self) -> bool:
        return bool(self.microsoft_client_id and self.microsoft_client_secret and self.credential_keys)

    @classmethod
    def from_environment(cls):
        model, runtime = None, None
        names = ("MODEL_PROVIDER", "MODEL_ID", "MODEL_API_KEY", "RUNTIME_STATE_ROOT", "RUNTIME_IMAGE")
        values = {name: os.environ.get("ALPENDATA_" + name, "") for name in names}
        if any(values.values()):
            if not all(values.values()):
                raise ValueError("Chat requires model provider, model ID, credential, state root and image")
            model = ModelSettings(
                values["MODEL_PROVIDER"],
                values["MODEL_ID"],
                values["MODEL_API_KEY"],
                allowed_providers=tuple(
                    filter(
                        None,
                        (
                            name.strip()
                            for name in os.environ.get("ALPENDATA_MODEL_ALLOWED_PROVIDERS", "").split(",")
                        ),
                    )
                ),
            )
            runtime = RuntimeSettings(Path(values["RUNTIME_STATE_ROOT"]), values["RUNTIME_IMAGE"])
        return cls(
            database_url=os.environ.get("ALPENDATA_DATABASE_URL", ""),
            public_origin=os.environ.get("ALPENDATA_PUBLIC_ORIGIN", "https://localhost"),
            microsoft_client_id=os.environ.get("ALPENDATA_MICROSOFT_CLIENT_ID", ""),
            microsoft_client_secret=os.environ.get("ALPENDATA_MICROSOFT_CLIENT_SECRET", ""),
            credential_keys=tuple(filter(None, os.environ.get("ALPENDATA_CREDENTIAL_KEYS", "").split(","))),
            smtp_host=os.environ.get("ALPENDATA_SMTP_HOST", ""),
            smtp_port=int(os.environ.get("ALPENDATA_SMTP_PORT", "465")),
            smtp_sender=os.environ.get("ALPENDATA_SMTP_SENDER", ""),
            smtp_username=os.environ.get("ALPENDATA_SMTP_USERNAME", ""),
            smtp_password=os.environ.get("ALPENDATA_SMTP_PASSWORD", ""),
            model=model,
            runtime=runtime,
        )
