"""Delegated Graph tokens, kept in an encrypted MSAL cache per connection."""

from dataclasses import dataclass
from uuid import UUID

import msal
from requests import RequestException

from .microsoft_identity import MicrosoftIdentity, MicrosoftSignIn, validated_identity

SCOPES = {
    "mail": "Mail.Read",
    "calendar": "Calendars.Read",
    "files": "Files.Read.All",
    "files_write": "Files.ReadWrite.All",
}
CALLBACK = "/api/integrations/microsoft/callback"


def granted_scopes(result: dict) -> set[str]:
    return {
        scope.removeprefix("https://graph.microsoft.com/").casefold()
        for scope in result.get("scope", "").split()
    }


@dataclass
class Grant:
    identity: MicrosoftIdentity
    capabilities: list[str]
    cache: str


class MicrosoftData(MicrosoftSignIn):
    @staticmethod
    def tenant(identity: MicrosoftIdentity) -> str:
        tenant = str(UUID(identity.issuer.split("/")[-2]))
        if identity.issuer != f"https://login.microsoftonline.com/{tenant}/v2.0":
            raise ValueError("Microsoft identity is not supported")
        return tenant

    def begin_connection(self, capabilities: list[str], identity: MicrosoftIdentity) -> dict:
        tenant = self.tenant(identity)
        # Pin the data connection to the signed-in directory, including guest
        # accounts. MSAL's cache realm then represents that resource directory.
        flow = self.client(offline=True, tenant=tenant).initiate_auth_code_flow(
            scopes=[SCOPES[item] for item in capabilities],
            redirect_uri=self.settings.public_origin + CALLBACK,
            prompt="select_account",
            response_mode="form_post",
        )
        flow["capabilities"] = capabilities
        flow["tenant"] = tenant
        return flow

    def complete_connection(self, flow: dict, response: dict) -> Grant:
        cache = msal.SerializableTokenCache()
        client = self.client(token_cache=cache, offline=True, tenant=flow["tenant"])
        try:
            result = client.acquire_token_by_auth_code_flow(flow, response)
            identity = validated_identity(result["id_token_claims"], self.settings.microsoft_client_id)
        except (RuntimeError, ValueError, KeyError, TypeError):
            raise ValueError("Microsoft connection failed") from None
        capabilities = [
            item for item in flow["capabilities"] if SCOPES[item].casefold() in granted_scopes(result)
        ]
        if result.get("error") or not result.get("access_token") or not capabilities:
            raise ValueError("Microsoft permissions were not granted")
        accounts = client.get_accounts()
        if not any(self.matches(account, identity) for account in accounts):
            raise ValueError("Microsoft account cache is incomplete")
        return Grant(identity, capabilities, cache.serialize())

    @staticmethod
    def matches(account: dict, identity: MicrosoftIdentity) -> bool:
        return (
            account.get("local_account_id") == identity.subject
            and identity.issuer == f"https://login.microsoftonline.com/{account.get('realm')}/v2.0"
        )

    def access(self, serialized: str, identity: MicrosoftIdentity, capability: str):
        cache = msal.SerializableTokenCache()
        cache.deserialize(serialized)
        client = self.client(token_cache=cache, offline=True, tenant=self.tenant(identity))
        accounts = [account for account in client.get_accounts() if self.matches(account, identity)]
        if len(accounts) != 1:
            return None, cache.serialize()
        try:
            result = client.acquire_token_silent_with_error([SCOPES[capability]], account=accounts[0])
        except (RuntimeError, ValueError, KeyError, TypeError):
            return None, cache.serialize()
        # MSAL's cache hit omits `scope`; it already selects a token whose target
        # contains the requested scope. A new endpoint response includes scope.
        if result and result.get("error") in {"temporarily_unavailable", "server_error"}:
            # A provider outage does not revoke the user's consent or credentials.
            raise RequestException("Microsoft token service unavailable")
        if (
            not result
            or result.get("error")
            or (
                result.get("token_source") != "cache"
                and SCOPES[capability].casefold() not in granted_scopes(result)
            )
        ):
            return None, cache.serialize()
        return result.get("access_token"), cache.serialize()
