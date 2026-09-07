"""Personal calendar writes, with provider preconditions and no automatic retry."""

import json
from contextlib import nullcontext
from datetime import datetime, timezone
from urllib.parse import quote

import requests
from fastapi import HTTPException
from icalendar import Calendar, Event, vCalAddress

from .graph import GraphError
from .infomaniak_dav import decode_path, opaque_path


def graph_request(graph, token, method, event_id="", *, body=None, etag=None):
    url = "https://graph.microsoft.com/v1.0/me/events" + ("/" + quote(event_id, safe="") if event_id else "")
    try:
        with nullcontext(graph.session) if graph.session is not None else requests.Session() as transport:
            transport.trust_env = False
            with transport.request(
                method,
                url,
                json=body,
                headers={
                    "Authorization": "Bearer " + token,
                    "Accept": "application/json",
                    **({"If-Match": etag} if etag else {}),
                },
                timeout=(5, 20),
                allow_redirects=False,
                stream=True,
            ) as response:
                if response.status_code == 401:
                    raise GraphError(409, "microsoft_reconnect_required")
                if response.status_code in (400, 403, 404, 409, 412, 422, 429):
                    raise GraphError(
                        409, "calendar_changed" if response.status_code == 412 else "calendar_rejected"
                    )
                if response.status_code not in (200, 201):
                    raise GraphError(
                        502, "calendar_result_unknown" if method != "GET" else "calendar_unavailable"
                    )
                content = bytearray()
                for chunk in response.iter_content(16384):
                    content.extend(chunk)
                    if len(content) > 200000:
                        raise ValueError()
                result = json.loads(content)
                if not isinstance(result.get("id"), str):
                    raise ValueError()
                result["etag"] = response.headers.get("ETag") or result.get("@odata.etag")
                return result
    except (requests.RequestException, ValueError, AttributeError):
        raise GraphError(
            502, "calendar_result_unknown" if method != "GET" else "calendar_unavailable"
        ) from None


def graph_prepare(graph, token, event_id):
    if not event_id:
        return {}
    result = graph_request(graph, token, "GET", event_id)
    if result.get("type") != "singleInstance" or not result.get("etag"):
        raise GraphError(409, "calendar_manual_edit_required")
    return {
        "event_id": event_id,
        "etag": result["etag"],
        "subject": result.get("subject", ""),
        "start": result.get("start"),
        "end": result.get("end"),
    }


def graph_write(graph, token, action_id, data, baseline):
    event_id = data.get("event_id", "")
    body = {
        "subject": data["subject"],
        "body": {"contentType": "Text", "content": data["description"]},
        "start": {
            "dateTime": datetime.fromisoformat(data["start"]).replace(tzinfo=None).isoformat(),
            "timeZone": "UTC",
        },
        "end": {
            "dateTime": datetime.fromisoformat(data["end"]).replace(tzinfo=None).isoformat(),
            "timeZone": "UTC",
        },
        "location": {"displayName": data["location"]},
        "attendees": [
            {"emailAddress": {"address": address}, "type": "required"} for address in data["attendees"]
        ],
    }
    if not event_id:
        body["transactionId"] = action_id
    result = graph_request(
        graph,
        token,
        "PATCH" if event_id else "POST",
        event_id,
        body=body,
        etag=baseline.get("etag") if event_id else None,
    )
    return {"event_id": result["id"], "etag": result.get("etag"), "url": result.get("webLink")}


def dav_prepare(dav, credentials, data):
    service = credentials.get("calendar")
    if not service:
        raise HTTPException(409, "infomaniak_reconnect_required")
    calendars = dav.calendars(service)
    calendar_id = data.get("calendar_id") or (calendars[0]["id"] if len(calendars) == 1 else None)
    calendar = next((item for item in calendars if item["id"] == calendar_id), None)
    if calendar is None:
        raise HTTPException(409, "calendar_selection_required")
    addresses = calendar.get("organizer_addresses", [])
    baseline = {
        "calendar_id": calendar_id,
        "calendar_name": calendar["name"],
        "organizer": addresses[0] if addresses else None,
    }
    if data.get("attendees") and not addresses:
        raise HTTPException(409, "calendar_scheduling_unavailable")
    if data.get("event_id"):
        path = decode_path(data["event_id"])
        if not path.startswith(decode_path(calendar_id).rstrip("/") + "/"):
            raise HTTPException(422, "calendar_event_mismatch")
        content, headers = dav.request(service, "https://sync.infomaniak.com", "GET", path)
        if len(content) > 100000:
            raise HTTPException(422, "calendar_manual_edit_required")
        try:
            events = Calendar.from_ical(content).walk("VEVENT")
            etag = headers.get("ETag") or headers.get("etag")
            if len(events) != 1 or any(key in events[0] for key in ("RRULE", "RECURRENCE-ID")) or not etag:
                raise ValueError()
            organizer = str(events[0].get("ORGANIZER", ""))
            if organizer and organizer.casefold() not in {address.casefold() for address in addresses}:
                raise HTTPException(409, "calendar_not_organizer")
            if organizer:
                baseline["organizer"] = organizer
            baseline.update(ical=content.decode(), etag=etag, subject=str(events[0].get("SUMMARY", "")))
        except (ValueError, KeyError, UnicodeError):
            raise HTTPException(409, "calendar_manual_edit_required") from None
    return baseline


def dav_write(dav, credentials, action_id, data, baseline):
    service = credentials.get("calendar")
    if not service:
        raise HTTPException(409, "infomaniak_reconnect_required")
    if data.get("event_id"):
        calendar = Calendar.from_ical(baseline["ical"])
        event = calendar.walk("VEVENT")[0]
        path = decode_path(data["event_id"])
        condition = {"If-Match": baseline["etag"]}
    else:
        calendar, event = Calendar(), Event()
        calendar.add("prodid", "-//AlpenData//Work Assistant//EN")
        calendar.add("version", "2.0")
        event.add("uid", action_id + "@agent.alpendata.ch")
        calendar.add_component(event)
        path = decode_path(baseline["calendar_id"]).rstrip("/") + "/" + action_id + ".ics"
        condition = {"If-None-Match": "*"}
    for key in ("summary", "description", "location", "dtstart", "dtend", "duration", "attendee", "dtstamp"):
        event.pop(key, None)
    for key in ("subject", "description", "location"):
        event.add("summary" if key == "subject" else key, data[key])
    event.add("dtstart", datetime.fromisoformat(data["start"]))
    event.add("dtend", datetime.fromisoformat(data["end"]))
    event.add("dtstamp", datetime.now(timezone.utc))
    if data["attendees"]:
        if not baseline.get("organizer"):
            raise HTTPException(409, "calendar_scheduling_unavailable")
        event["organizer"] = vCalAddress(baseline["organizer"])
    for address in data["attendees"]:
        attendee = vCalAddress("mailto:" + address)
        attendee.params.update({"PARTSTAT": "NEEDS-ACTION", "ROLE": "REQ-PARTICIPANT", "RSVP": "TRUE"})
        event.add("attendee", attendee)
    event["sequence"] = int(event.get("sequence", 0)) + 1
    _, headers = dav.request(
        service,
        "https://sync.infomaniak.com",
        "PUT",
        path,
        calendar.to_ical(),
        {**condition, "Content-Type": "text/calendar; charset=utf-8"},
        statuses=(200, 201, 204),
    )
    return {
        "event_id": opaque_path(path),
        "etag": headers.get("ETag") or headers.get("etag"),
        "url": "https://calendar.infomaniak.com/",
    }
