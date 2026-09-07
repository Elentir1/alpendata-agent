import base64
from datetime import datetime, timezone
from xml.sax.saxutils import escape

import pytest
from fastapi import HTTPException
from service_http import service_http

from alpendata_api.calendar_provider import dav_prepare, dav_write
from alpendata_api.infomaniak_dav import InfomaniakDav, opaque_path


def multistatus(inner):
    return (
        '<d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">' + inner + "</d:multistatus>"
    ).encode()


def test_dav_does_not_forward_credentials_to_another_origin_or_follow_redirects():
    credentials = {"username": "synthetic-user", "password": "synthetic-password"}
    body = multistatus(
        "<d:response><d:propstat><d:prop><d:current-user-principal>"
        "<d:href>https://untrusted.example/principal</d:href></d:current-user-principal>"
        "</d:prop></d:propstat></d:response>"
    )
    with service_http(lambda _: (207, {}, body)) as (transport, calls):
        dav = InfomaniakDav(transport)
        with pytest.raises(HTTPException) as error:
            dav.calendars(credentials)
        assert error.value.detail == "infomaniak_path_invalid"
        assert len(calls) == 1
        assert (
            calls[0]["headers"]["Authorization"]
            == "Basic " + base64.b64encode(b"synthetic-user:synthetic-password").decode()
        )
    with service_http(lambda _: (302, {"Location": "https://untrusted.example/"}, b"")) as (transport, calls):
        with pytest.raises(HTTPException):
            InfomaniakDav(transport).properties(credentials, "https://sync.infomaniak.com", "/")
        assert len(calls) == 1


def test_kdrive_search_and_download_use_the_same_private_drive():
    listing = multistatus(
        "<d:response><d:href>/</d:href><d:propstat><d:prop><d:resourcetype><d:collection/>"
        "</d:resourcetype></d:prop></d:propstat></d:response><d:response><d:href>/Client%20brief.txt</d:href>"
        "<d:propstat><d:prop><d:getetag>version-1</d:getetag></d:prop></d:propstat></d:response>"
    )
    credentials = {"username": "synthetic-user", "password": "synthetic-password", "drive_id": "12345"}
    with service_http(
        lambda request: (207, {}, listing) if request["method"] == "PROPFIND" else (200, {}, b"Private brief")
    ) as (transport, calls):
        dav = InfomaniakDav(transport)
        result = dav.files(credentials, "brief")
        assert result["files"][0]["name"] == "Client brief.txt"
        assert result["search_scope"] == "filenames"
        file = result["files"][0]
        read = dav.download(credentials, file["drive_id"], file["id"])
        assert read["files"][0]["name"] == "Client brief.txt"
        assert base64.b64decode(read["content_base64"]) == b"Private brief"
        with pytest.raises(HTTPException):
            dav.download(credentials, "54321", file["id"])
        with pytest.raises(HTTPException):
            dav.download(credentials, "12345", opaque_path("https://untrusted.example/secret"))
        assert len(calls) == 2


def test_calendar_discovery_uses_real_organizer_and_normalizes_offsets_before_inviting():
    from icalendar import Calendar

    principal = multistatus(
        "<d:response><d:propstat><d:prop>"
        "<c:calendar-user-address-set><d:href>mailto:coach@example.com</d:href></c:calendar-user-address-set>"
        "<c:calendar-home-set><d:href>/calendars/</d:href></c:calendar-home-set>"
        "</d:prop></d:propstat></d:response>"
    )
    calendars = multistatus(
        "<d:response><d:href>/calendars/personal/</d:href><d:propstat><d:prop>"
        "<d:resourcetype><c:calendar/></d:resourcetype><d:displayname>Personal</d:displayname>"
        "</d:prop></d:propstat></d:response>"
    )
    event = (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:one\r\n"
        "DTSTART;TZID=Europe/Zurich:20261005T100000\r\nDTEND;TZID=Europe/Zurich:20261005T110000\r\n"
        "SUMMARY:Client\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
    )
    report = multistatus(
        "<d:response><d:href>/calendars/personal/one.ics</d:href><d:propstat><d:prop><c:calendar-data>"
        + escape(event)
        + "</c:calendar-data></d:prop></d:propstat></d:response>"
    )

    def respond(request):
        if request["method"] == "PUT":
            return 201, {}, b""
        if request["method"] == "REPORT":
            return 207, {}, report
        return 207, {}, calendars if request["path"] == "/calendars/" else principal

    credentials = {"username": "opaque-sync-login", "password": "synthetic-password"}
    data = {
        "subject": "Client",
        "start": "2026-10-05T10:00:00+02:00",
        "end": "2026-10-05T11:00:00+02:00",
        "attendees": ["client@example.com"],
        "description": "",
        "location": "",
    }
    with service_http(respond) as (transport, calls):
        dav = InfomaniakDav(transport)
        item = dav.calendar(credentials)["events"][0]
        assert datetime.fromisoformat(item["start"]["dateTime"]) == datetime(
            2026, 10, 5, 8, tzinfo=timezone.utc
        )
        assert item["start"]["dateTime"].endswith("+00:00")
        baseline = dav_prepare(dav, {"calendar": credentials}, data)
        assert baseline["organizer"] == "mailto:coach@example.com"
        dav_write(dav, {"calendar": credentials}, "one-action", data, baseline)
        written = Calendar.from_ical(calls[-1]["body"]).walk("VEVENT")[0]
        assert str(written["organizer"]) == "mailto:coach@example.com"
        assert written["attendee"].params["RSVP"] == "TRUE"
        count = len(calls)
        with pytest.raises(HTTPException) as error:
            dav_write(dav, {"calendar": credentials}, "other-action", data, {**baseline, "organizer": None})
        assert error.value.detail == "calendar_scheduling_unavailable" and len(calls) == count
