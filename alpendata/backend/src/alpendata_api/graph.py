"""Bounded read operations. No caller-supplied URL, mailbox or Graph method."""

import json
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import requests


class GraphError(Exception):
    def __init__(self, status: int, code: str, retry_after: int = 0):
        self.status, self.code, self.retry_after = status, code, retry_after
        super().__init__(code)


def web_link(value):
    if isinstance(value, str) and len(value) <= 4096:
        try:
            parsed = urlsplit(value)
        except ValueError:
            return None
        if parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password:
            return value
    return None


def object_value(value):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise GraphError(502, "microsoft_read_failed")
    return value


def items(value, limit):
    if not isinstance(value, list):
        raise GraphError(502, "microsoft_read_failed")
    return [object_value(item) for item in value[:limit]]


class GraphReader:
    def __init__(self, session=None, *, content_session=None):
        self.session = session
        self.content_session = content_session

    def request(self, token, method, path, *, params=None, body=None):
        try:
            # Do not share HTTP cookies or mutable Session state between users.
            with nullcontext(self.session) if self.session is not None else requests.Session() as transport:
                transport.trust_env = False
                with transport.request(
                    method,
                    "https://graph.microsoft.com/v1.0" + path,
                    params=params,
                    json=body,
                    headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
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
                        delay = response.headers.get("Retry-After", "60")
                        raise GraphError(
                            429,
                            "microsoft_rate_limited",
                            min(3600, max(1, int(delay))) if delay.isdigit() else 60,
                        )
                    if response.status_code != 200:
                        raise GraphError(502, "microsoft_read_failed")
                    content = bytearray()
                    for chunk in response.iter_content(65536):
                        content.extend(chunk)
                        if len(content) > 2 * 1024 * 1024:
                            raise GraphError(502, "microsoft_response_too_large")
                    data = json.loads(content)
                    if not isinstance(data, dict):
                        raise GraphError(502, "microsoft_read_failed")
                    return data
        except (requests.RequestException, ValueError):
            raise GraphError(502, "microsoft_read_failed") from None

    def mail(self, token, query=""):
        data = self.request(
            token,
            "GET",
            "/me/messages",
            params={
                "$top": 10,
                **({"$search": json.dumps(query)} if query else {"$orderby": "receivedDateTime desc"}),
                "$select": "id,subject,from,receivedDateTime,bodyPreview,webLink,isRead",
            },
        )
        return {
            "messages": [
                {
                    "id": item.get("id"),
                    "subject": item.get("subject", ""),
                    "sender": object_value(object_value(item.get("from")).get("emailAddress")).get(
                        "name", ""
                    ),
                    "received_at": item.get("receivedDateTime"),
                    "sender_address": object_value(object_value(item.get("from")).get("emailAddress")).get(
                        "address", ""
                    ),
                    "preview": item.get("bodyPreview", ""),
                    "url": web_link(item.get("webLink")),
                    "is_read": item.get("isRead", False),
                }
                for item in items(data.get("value", []), 10)
            ]
        }

    def calendar(self, token):
        start = datetime.now(timezone.utc)
        data = self.request(
            token,
            "GET",
            "/me/calendarView",
            params={
                "startDateTime": start.isoformat(),
                "endDateTime": (start + timedelta(days=7)).isoformat(),
                "$top": 20,
                "$orderby": "start/dateTime",
                "$select": "id,subject,start,end,webLink",
            },
        )
        return {
            "events": [
                {
                    "id": item.get("id"),
                    "subject": item.get("subject", ""),
                    "start": item.get("start"),
                    "end": item.get("end"),
                    "url": web_link(item.get("webLink")),
                }
                for item in items(data.get("value", []), 20)
            ]
        }

    def files(self, token, query):
        data = self.request(
            token,
            "POST",
            "/search/query",
            body={
                "requests": [
                    {
                        "entityTypes": ["driveItem"],
                        "query": {"queryString": query},
                        "from": 0,
                        "size": 10,
                    }
                ]
            },
        )
        files = []
        for response in items(data.get("value", []), 1):
            for container in items(response.get("hitsContainers", []), 1):
                for hit in items(container.get("hits", []), 10):
                    item = object_value(hit.get("resource"))
                    files.append(
                        {
                            "id": item.get("id"),
                            "name": item.get("name", ""),
                            "drive_id": object_value(item.get("parentReference")).get("driveId"),
                            "url": web_link(item.get("webUrl")),
                            "modified_at": item.get("lastModifiedDateTime"),
                        }
                    )
        return {"files": files}
