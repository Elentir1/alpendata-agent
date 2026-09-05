"""Encrypted server-side payloads bound to their intended owner or flow."""

import json

from cryptography.fernet import Fernet, InvalidToken, MultiFernet


class Vault:
    def __init__(self, keys: tuple[str, ...]):
        if not keys:
            raise ValueError("A credential encryption key is required")
        # First key encrypts; remaining keys allow a controlled rotation.
        self.cipher = MultiFernet([Fernet(key.encode("ascii")) for key in keys])

    def seal(self, context: str, value: dict) -> str:
        payload = json.dumps({"context": context, "value": value}, ensure_ascii=False).encode("utf-8")
        return self.cipher.encrypt(payload).decode("ascii")

    def open(self, context: str, ciphertext: str) -> dict:
        payload = json.loads(self.cipher.decrypt(ciphertext.encode("ascii")))
        if payload.get("context") != context or not isinstance(payload.get("value"), dict):
            raise InvalidToken("Encrypted payload belongs to another context")
        return payload["value"]
