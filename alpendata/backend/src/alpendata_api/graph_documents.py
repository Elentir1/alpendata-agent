"""Personal Graph file downloads; preauthenticated links never leave the broker."""

import base64
from contextlib import nullcontext
from urllib.parse import quote, urlsplit

import requests
from pydantic import BaseModel, ConfigDict, Field

from .graph import GraphError, web_link

MAX_FILE_BYTES = 5 * 1024 * 1024


class FileInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    drive_id: str = Field(min_length=1, max_length=512, pattern=r"^[A-Za-z0-9!_-]+$")
    item_id: str = Field(min_length=1, max_length=512, pattern=r"^[A-Za-z0-9!_-]+$")


def download_url(value):
    try:
        parsed = urlsplit(value)
        valid = (
            isinstance(value, str)
            and len(value) <= 8192
            and parsed.scheme == "https"
            and not parsed.username
            and not parsed.password
            and parsed.port in (None, 443)
            and not parsed.fragment
            and not any(ord(character) < 33 for character in value)
            and any(
                (parsed.hostname or "").endswith("." + domain)
                for domain in ("sharepoint.com", "sharepointonline.com", "1drv.com")
            )
        )
    except (ValueError, TypeError, AttributeError):
        valid = False
    if not valid:
        raise GraphError(502, "microsoft_download_destination_invalid")
    return value


def content_download(graph, token, *, drive_id, item_id):
    """Only the fixed Graph authority receives an OAuth token."""
    data = FileInput(drive_id=drive_id, item_id=item_id)
    path = f"/drives/{quote(data.drive_id, safe='')}/items/{quote(data.item_id, safe='')}"
    metadata = graph.request(token, "GET", path, params={"$select": "id,name,size,file,eTag,webUrl"})
    size = metadata.get("size")
    if not isinstance(metadata.get("file"), dict):
        raise GraphError(400, "microsoft_item_not_a_file")
    if type(size) is not int or size < 0 or size > MAX_FILE_BYTES:
        raise GraphError(413, "microsoft_file_too_large")
    if (
        not isinstance(metadata.get("name"), str)
        or not metadata["name"]
        or len(metadata["name"]) > 1024
        or not isinstance(metadata.get("eTag"), str)
        or not 1 <= len(metadata["eTag"]) <= 1024
        or metadata.get("id") != data.item_id
    ):
        raise GraphError(502, "microsoft_read_failed")
    try:
        with nullcontext(graph.session) if graph.session is not None else requests.Session() as transport:
            transport.trust_env = False
            with transport.request(
                "GET",
                "https://graph.microsoft.com/v1.0" + path + "/content",
                headers={"Authorization": "Bearer " + token},
                timeout=20,
                allow_redirects=False,
                stream=True,
            ) as response:
                if response.status_code == 401:
                    raise GraphError(409, "microsoft_reconnect_required")
                if response.status_code == 403:
                    raise GraphError(403, "microsoft_access_denied")
                if response.status_code == 404:
                    raise GraphError(404, "microsoft_item_not_found")
                if response.status_code == 429:
                    raise GraphError(429, "microsoft_rate_limited")
                if response.status_code != 302:
                    raise GraphError(502, "microsoft_file_download_failed")
                url = download_url(response.headers.get("Location"))
        # Separate session: no Graph authorization, cookies, .netrc or redirects.
        with (
            nullcontext(graph.content_session)
            if graph.content_session is not None
            else requests.Session() as transport
        ):
            transport.trust_env = False
            with transport.request(
                "GET", url, headers={}, timeout=20, allow_redirects=False, stream=True
            ) as response:
                if response.status_code != 200:
                    raise GraphError(502, "microsoft_file_download_failed")
                content = bytearray()
                for chunk in response.iter_content(65536):
                    content.extend(chunk)
                    if len(content) > MAX_FILE_BYTES:
                        raise GraphError(413, "microsoft_file_too_large")
        # Reject an intervening edit, including same-size changes, before offering a source snapshot.
        latest = graph.request(token, "GET", path, params={"$select": "id,eTag"})
        if latest.get("id") != data.item_id or latest.get("eTag") != metadata["eTag"] or len(content) != size:
            raise GraphError(409, "microsoft_file_changed")
    except requests.RequestException:
        raise GraphError(502, "microsoft_file_download_failed") from None
    return {
        "files": [
            {
                "id": data.item_id,
                "drive_id": data.drive_id,
                "name": metadata["name"],
                "etag": metadata["eTag"],
                "url": web_link(metadata.get("webUrl")),
                "size": len(content),
            }
        ],
        "content_base64": base64.b64encode(content).decode("ascii"),
    }
