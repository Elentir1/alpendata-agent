"""Microsoft sign-in through MSAL's authorization-code flow, including PKCE and nonce.

This authenticates an AlpenData user. It does not create a personal Graph connection.
Email/UPN claims are never treated as a verified address or used to merge accounts.
"""

import logging
from dataclasses import dataclass
from uuid import UUID

import msal

from .models import now
from .settings import Settings

PERSONAL_MICROSOFT_TENANT = "9188040d-6c67-4c5b-b112-36a304b66dad"


class _NoIdentityDetails(logging.Filter):
    def filter(self, record):
        # MSAL's OIDC time warnings include decoded claims even with PII logging
        # disabled. Keep the diagnostic event without retaining those claims.
        record.msg = "Microsoft OIDC validation event (identity details omitted)"
        record.args = ()
        record.exc_info = None
        record.exc_text = None
        return True


logging.getLogger("msal.oauth2cli.oidc").addFilter(_NoIdentityDetails())


@dataclass(frozen=True)
class MicrosoftIdentity:
    issuer: str
    subject: str
    display_name: str
    cache_realm: str | None = None


class MicrosoftSignIn:
    def __init__(self, settings: Settings, *, http_client=None):
        self.settings = settings
        self.http_client = http_client

    def client(self, *, token_cache=None, offline=False, tenant="organizations"):
        if tenant != "organizations":
            tenant = str(UUID(tenant))
        return msal.ConfidentialClientApplication(
            self.settings.microsoft_client_id,
            client_credential=self.settings.microsoft_client_secret,
            authority="https://login.microsoftonline.com/" + tenant,
            timeout=20,
            http_client=self.http_client,
            exclude_scopes=[] if offline else ["offline_access"],
            token_cache=token_cache,
            enable_pii_log=False,
        )

    def begin(self) -> dict:
        return self.client().initiate_auth_code_flow(
            scopes=[],
            redirect_uri=self.settings.public_origin + "/api/auth/microsoft/callback",
            prompt="select_account",
            response_mode="form_post",
        )

    def complete(self, flow: dict, response: dict) -> MicrosoftIdentity:
        try:
            result = self.client().acquire_token_by_auth_code_flow(flow, response)
        except (RuntimeError, ValueError, KeyError, TypeError):
            # MSAL exceptions can contain decoded identity claims. Do not retain
            # them in an exception chain exposed to application logging.
            raise ValueError("Microsoft authentication failed") from None
        claims = result.get("id_token_claims")
        if result.get("error") or not isinstance(claims, dict):
            raise ValueError("Microsoft authentication failed")
        return validated_identity(claims, self.settings.microsoft_client_id)


def validated_identity(claims: dict, client_id: str) -> MicrosoftIdentity:
    # MSAL checks the token exchange and OIDC claims. We additionally constrain
    # this product to organizational accounts with a tenant-scoped immutable ID.
    try:
        tenant = str(UUID(claims["tid"]))
        subject = str(UUID(claims["oid"]))
    except (KeyError, ValueError, TypeError, AttributeError) as error:
        raise ValueError("Microsoft identity is incomplete") from error
    issuer = f"https://login.microsoftonline.com/{tenant}/v2.0"
    current = now()
    if (
        claims.get("iss") != issuer
        or claims.get("aud") != client_id
        or tenant == PERSONAL_MICROSOFT_TENANT
        or type(claims.get("exp")) is not int
        or claims["exp"] <= current
        or type(claims.get("iat")) is not int
        or claims["iat"] > current + 120
        or type(claims.get("nbf", current)) is not int
        or claims.get("nbf", current) > current + 120
    ):
        raise ValueError("Microsoft identity is not supported")
    name = claims.get("name")
    return MicrosoftIdentity(issuer, subject, name[:160] if isinstance(name, str) else "Microsoft user")
