"""Immutable private objects. Swift URLs are operator-owned, never supplied by a model."""

import hashlib
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

import requests
from fastapi import HTTPException

LIMIT = 5 * 1024 * 1024


@dataclass(frozen=True)
class FileStoreSettings:
    root: Path | None = None
    swift_container_url: str = ""
    swift_token: str = field(default="", repr=False)

    def __post_init__(self):
        if bool(self.swift_container_url) != bool(self.swift_token):
            raise ValueError("Swift requires an authenticated private container")
        if self.swift_container_url:
            url = urlsplit(self.swift_container_url)
            if (
                url.scheme != "https"
                or not url.hostname
                or url.username
                or url.password
                or url.query
                or url.fragment
            ):
                raise ValueError("Swift container must be an HTTPS URL")
        if self.root and not self.root.is_absolute():
            raise ValueError("Private object storage requires an absolute directory")
        if not self.root and not self.swift_container_url:
            raise ValueError("Private object storage is not configured")


class FileStore:
    def __init__(self, settings):
        self.settings = settings

    def key(self, key):
        if not re.fullmatch(r"[0-9a-f-]{36}/[0-9a-f-]{36}/[0-9a-f]{64}", key):
            raise HTTPException(400, "document_key_invalid")
        return key

    def put(self, organization_id, owner_id, content):
        if not content or len(content) > LIMIT:
            raise HTTPException(413, "document_too_large")
        digest = hashlib.sha256(content).hexdigest()
        key = self.key(f"{organization_id}/{owner_id}/{digest}")
        if self.settings.swift_container_url:
            self.request("PUT", key, content)
        else:
            path = self.settings.root / key
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            if not path.exists():
                # A reader must never see a partially written immutable object.
                descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".upload-")
                try:
                    with os.fdopen(descriptor, "wb") as target:
                        target.write(content)
                        target.flush()
                        os.fsync(target.fileno())
                    try:
                        os.link(temporary, path)
                    except FileExistsError:
                        pass
                finally:
                    Path(temporary).unlink(missing_ok=True)
        return key, digest

    def get(self, key):
        self.key(key)
        if self.settings.swift_container_url:
            content = self.request("GET", key)
        else:
            try:
                with (self.settings.root / key).open("rb") as source:
                    content = source.read(LIMIT + 1)
            except OSError:
                raise HTTPException(503, "document_storage_unavailable") from None
        if len(content) > LIMIT or hashlib.sha256(content).hexdigest() != key.rsplit("/", 1)[1]:
            raise HTTPException(503, "document_integrity_failed")
        return content

    def request(self, method, key, content=None):
        try:
            with requests.Session() as transport:
                transport.trust_env = False
                with transport.request(
                    method,
                    self.settings.swift_container_url.rstrip("/") + "/" + key,
                    data=content,
                    headers={
                        "X-Auth-Token": self.settings.swift_token,
                        "Content-Type": "application/octet-stream",
                    },
                    timeout=(5, 20),
                    allow_redirects=False,
                    stream=True,
                ) as response:
                    if response.status_code not in (200, 201, 202):
                        raise HTTPException(503, "document_storage_unavailable")
                    data = bytearray()
                    for chunk in response.iter_content(65536):
                        data.extend(chunk)
                        if len(data) > LIMIT:
                            raise HTTPException(413, "document_too_large")
                    return bytes(data)
        except requests.RequestException:
            raise HTTPException(503, "document_storage_unavailable") from None
