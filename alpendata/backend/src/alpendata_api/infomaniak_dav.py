"""Bounded DAV operations restricted to the user's configured Infomaniak services."""

import base64
import hashlib
import re
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote, urljoin, urlsplit

import requests
from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException
from fastapi import HTTPException
from icalendar import Calendar
from pydantic import Field

from .file_store import LIMIT
from .schemas import Input

DAV = "DAV:"
CAL = "urn:ietf:params:xml:ns:caldav"


class DavFileInput(Input):
    drive_id: str = Field(pattern=r"^[1-9][0-9]{0,15}$")
    item_id: str = Field(min_length=1, max_length=2048, pattern=r"^[A-Za-z0-9_-]+$")


def safe_url(origin, value):
    url = urljoin(origin + "/", value)
    parsed = urlsplit(url)
    if (
        parsed.scheme + "://" + parsed.netloc != origin
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or "\\" in unquote(parsed.path)
        or any(part in (".", "..") for part in unquote(parsed.path).split("/"))
    ):
        raise HTTPException(400, "infomaniak_path_invalid")
    return url


def drive_origin(identifier):
    if not re.fullmatch(r"[1-9][0-9]{0,15}", str(identifier)):
        raise HTTPException(400, "infomaniak_drive_invalid")
    return "https://" + str(identifier) + ".connect.kdrive.infomaniak.com"


def opaque_path(value):
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


def decode_path(value):
    try:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,2048}", value):
            raise ValueError
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)).decode()
    except (ValueError, UnicodeError):
        raise HTTPException(400, "infomaniak_path_invalid") from None


class InfomaniakDav:
    def __init__(self, session=None):
        self.session = session

    def request(
        self, credentials, origin, method, path, body=None, headers=None, statuses=(200, 207), missing=False
    ):
        url = safe_url(origin, path)
        try:
            with nullcontext(self.session) if self.session is not None else requests.Session() as transport:
                transport.trust_env = False
                with transport.request(
                    method,
                    url,
                    auth=(credentials["username"], credentials["password"]),
                    data=body,
                    headers=headers or {},
                    timeout=(5, 20),
                    allow_redirects=False,
                    stream=True,
                ) as response:
                    if missing and response.status_code == 404:
                        return None, {}
                    if response.status_code in (401, 403):
                        raise HTTPException(409, "infomaniak_connection_failed")
                    if response.status_code == 412:
                        raise HTTPException(409, "document_version_changed")
                    if response.status_code not in statuses:
                        raise HTTPException(
                            502, "infomaniak_write_unknown" if method == "PUT" else "infomaniak_read_failed"
                        )
                    content = bytearray()
                    for chunk in response.iter_content(65536):
                        content.extend(chunk)
                        if len(content) > LIMIT:
                            raise HTTPException(
                                502 if method == "PUT" else 413,
                                "infomaniak_write_unknown" if method == "PUT" else "document_too_large",
                            )
                    return bytes(content), dict(response.headers)
        except requests.RequestException:
            raise HTTPException(
                502, "infomaniak_write_unknown" if method == "PUT" else "infomaniak_read_failed"
            ) from None

    def properties(self, credentials, origin, path, depth="0", missing=False):
        body = (
            '<d:propfind xmlns:d="DAV:" xmlns:c="' + CAL + '"><d:prop>'
            "<d:current-user-principal/><c:calendar-home-set/><d:resourcetype/>"
            "<d:displayname/><d:getetag/><d:getcontentlength/><c:calendar-user-address-set/>"
            "</d:prop></d:propfind>"
        )
        data, _ = self.request(
            credentials,
            origin,
            "PROPFIND",
            path,
            body.encode(),
            {"Depth": depth, "Content-Type": "application/xml"},
            missing=missing,
        )
        if data is None:
            return None
        return self.xml(data)

    def xml(self, data):
        try:
            return ElementTree.fromstring(data)
        except (ElementTree.ParseError, ValueError, DefusedXmlException):
            raise HTTPException(502, "infomaniak_response_invalid") from None

    def calendars(self, credentials):
        origin = "https://sync.infomaniak.com"
        configured = credentials.get("url") or origin + "/"
        root = self.properties(credentials, origin, configured)
        principal = root.findtext(".//{" + DAV + "}current-user-principal/{" + DAV + "}href")
        if principal:
            root = self.properties(credentials, origin, principal)
        addresses = [
            node.text
            for node in root.findall(".//{" + CAL + "}calendar-user-address-set/{" + DAV + "}href")
            if node.text
            and node.text.lower().startswith("mailto:")
            and "@" in node.text
            and len(node.text) <= 327
            and not any(char.isspace() for char in node.text)
        ]
        home = root.findtext(".//{" + CAL + "}calendar-home-set/{" + DAV + "}href")
        root = self.properties(credentials, origin, home or configured, "1")
        calendars = []
        for row in root.findall("{" + DAV + "}response")[:100]:
            if row.find(".//{" + CAL + "}calendar") is not None:
                href = row.findtext("{" + DAV + "}href", "")
                calendars.append(
                    {
                        "id": opaque_path(urlsplit(safe_url(origin, href)).path),
                        "name": row.findtext(".//{" + DAV + "}displayname", "Calendar"),
                        "organizer_addresses": addresses[:20],
                    }
                )
        if not calendars:
            raise HTTPException(409, "infomaniak_calendar_not_found")
        return calendars

    def calendar(self, credentials):
        origin, start = "https://sync.infomaniak.com", datetime.now(timezone.utc)
        end = start + timedelta(days=7)
        begin, stop = start.strftime("%Y%m%dT%H%M%SZ"), end.strftime("%Y%m%dT%H%M%SZ")
        body = (
            f'<c:calendar-query xmlns:d="DAV:" xmlns:c="{CAL}"><d:prop><d:getetag/>'
            f'<c:calendar-data><c:expand start="{begin}" end="{stop}"/></c:calendar-data></d:prop>'
            '<c:filter><c:comp-filter name="VCALENDAR"><c:comp-filter name="VEVENT">'
            f'<c:time-range start="{begin}" end="{stop}"/></c:comp-filter></c:comp-filter>'
            "</c:filter></c:calendar-query>"
        )
        events, truncated = [], False
        calendars = self.calendars(credentials)
        for calendar in calendars[:10]:
            data, _ = self.request(
                credentials,
                origin,
                "REPORT",
                decode_path(calendar["id"]),
                body.encode(),
                {"Depth": "1", "Content-Type": "application/xml"},
            )
            rows = self.xml(data).findall("{" + DAV + "}response")
            truncated = truncated or len(rows) > 200
            for row in rows[:200]:
                text = row.findtext(".//{" + CAL + "}calendar-data")
                if not text:
                    continue
                try:
                    components = Calendar.from_ical(text).walk("VEVENT")
                    truncated = truncated or len(components) > 200
                    for event in components[:200]:
                        first, last = event.decoded("DTSTART"), event.decoded("DTEND", None)
                        if isinstance(first, datetime):
                            if first.tzinfo is None:
                                truncated = True
                                continue
                            first = first.astimezone(timezone.utc)
                        if isinstance(last, datetime):
                            if last.tzinfo is None:
                                truncated = True
                                continue
                            last = last.astimezone(timezone.utc)
                        events.append(
                            {
                                "id": opaque_path(
                                    urlsplit(safe_url(origin, row.findtext("{" + DAV + "}href", ""))).path
                                ),
                                "calendar_id": calendar["id"],
                                "subject": str(event.get("SUMMARY", ""))[:1000],
                                "start": {"dateTime": first.isoformat(), "timeZone": "UTC"},
                                "end": {
                                    "dateTime": last.isoformat() if last else first.isoformat(),
                                    "timeZone": "UTC",
                                },
                                "etag": row.findtext(".//{" + DAV + "}getetag"),
                                "url": "https://calendar.infomaniak.com/",
                            }
                        )
                except (ValueError, KeyError, AttributeError):
                    truncated = True
        events.sort(key=lambda event: event["start"]["dateTime"])
        return {"events": events[:100], "partial": truncated or len(events) > 100 or len(calendars) > 10}

    def files(self, credentials, query=""):
        origin, pending, files, visited = drive_origin(credentials["drive_id"]), ["/"], [], set()
        truncated = False
        # Bounded breadth-first walk: WebDAV does not promise a full-text search API.
        while pending and len(visited) < 30 and len(files) < 50:
            path = pending.pop(0)
            if path in visited:
                continue
            visited.add(path)
            tree = self.properties(credentials, origin, path, "1")
            rows = tree.findall("{" + DAV + "}response")
            truncated = truncated or len(rows) > 500
            for row in rows[:500]:
                href = urlsplit(safe_url(origin, row.findtext("{" + DAV + "}href", ""))).path
                if href.rstrip("/") == path.rstrip("/"):
                    continue
                name = unquote(href.rstrip("/").rsplit("/", 1)[-1])
                if row.find(".//{" + DAV + "}collection") is not None:
                    if href not in visited and len(pending) < 500:
                        pending.append(href)
                    elif href not in visited:
                        truncated = True
                elif query.casefold() in name.casefold():
                    files.append(
                        {
                            "id": opaque_path(href),
                            "drive_id": str(credentials["drive_id"]),
                            "name": name,
                            "url": "https://ksuite.infomaniak.com/",
                            "etag": row.findtext(".//{" + DAV + "}getetag"),
                        }
                    )
        return {
            "files": files[:50],
            "partial": truncated or bool(pending) or len(files) > 50,
            "search_scope": "filenames",
            "folders_checked": len(visited),
        }

    def download(self, credentials, drive_id, item_id):
        if drive_id != str(credentials["drive_id"]):
            raise HTTPException(404, "resource_not_found")
        path = decode_path(item_id)
        data, _ = self.request(credentials, drive_origin(drive_id), "GET", path)
        filename = unquote(urlsplit(path).path.rsplit("/", 1)[-1])
        from .workspace_files import UploadInput, decode_upload

        encoded = base64.b64encode(data).decode()
        from uuid import uuid4

        _, media_type = decode_upload(
            UploadInput(filename=filename, content_base64=encoded, request_id=uuid4())
        )
        return {
            "files": [
                {
                    "name": filename,
                    "id": item_id,
                    "drive_id": drive_id,
                    "url": "https://ksuite.infomaniak.com/",
                    "size": len(data),
                }
            ],
            "filename": filename,
            "media_type": media_type,
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "content_base64": encoded,
            "source": {"kind": "files", "label": filename, "url": "https://ksuite.infomaniak.com/"},
        }
