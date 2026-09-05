import os
from dataclasses import dataclass, field
from urllib.parse import urlsplit


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

    @property
    def microsoft_enabled(self) -> bool:
        return bool(self.microsoft_client_id and self.microsoft_client_secret and self.credential_keys)

    @classmethod
    def from_environment(cls):
        return cls(
            database_url=os.environ.get("ALPENDATA_DATABASE_URL", ""),
            public_origin=os.environ.get("ALPENDATA_PUBLIC_ORIGIN", "https://localhost"),
            microsoft_client_id=os.environ.get("ALPENDATA_MICROSOFT_CLIENT_ID", ""),
            microsoft_client_secret=os.environ.get("ALPENDATA_MICROSOFT_CLIENT_SECRET", ""),
            credential_keys=tuple(filter(None, os.environ.get("ALPENDATA_CREDENTIAL_KEYS", "").split(","))),
        )
