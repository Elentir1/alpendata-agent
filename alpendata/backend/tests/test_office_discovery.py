import pytest
from fastapi import HTTPException
from service_http import service_http

from alpendata_api.office_discovery import editor_action


@pytest.mark.parametrize(
    "payload,status",
    [
        (
            b'<wopi-discovery><action ext="docx" name="edit" urlsrc="https://evil.example/browser/cool.html"/></wopi-discovery>',
            200,
        ),
        (b'<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><foo>&xxe;</foo>', 200),
        (b"<broken", 200),
        (b"X" * (1024 * 1024 + 1), 200),
        (b"", 302),
        (b"", 503),
    ],
)
def test_discovery_rejects_untrusted_actions_and_unusable_provider_responses(monkeypatch, payload, status):
    with service_http(lambda _: (status, {}, payload)) as (transport, _):
        monkeypatch.setattr("alpendata_api.office_discovery.requests.Session", lambda: transport)
        with pytest.raises(HTTPException) as caught:
            editor_action(
                "https://office.example.test", "docx", "fr", "https://app.example.test/wopi/session"
            )
        assert caught.value.status_code == 503


def test_discovery_removes_optional_placeholders_and_scopes_the_wopi_url(monkeypatch):
    payload = b'<wopi-discovery><action ext="docx" name="edit" urlsrc="https://office.example.test/browser/version/cool.html?&lt;ui=UI_LLCC&amp;&gt;&amp;WOPISrc=https://wrong.example/&amp;"/></wopi-discovery>'
    with service_http(lambda _: (200, {}, payload)) as (transport, _):
        monkeypatch.setattr("alpendata_api.office_discovery.requests.Session", lambda: transport)
        action = editor_action(
            "https://office.example.test", "docx", "fr", "https://app.example.test/wopi/session"
        )
        from urllib.parse import parse_qs, urlsplit

        assert parse_qs(urlsplit(action).query) == {
            "lang": ["fr"],
            "WOPISrc": ["https://app.example.test/wopi/session"],
        }


def test_editor_requires_a_separate_browser_origin():
    from alpendata_api.settings import Settings

    with pytest.raises(ValueError, match="separate HTTPS origin"):
        Settings(
            database_url="sqlite://",
            public_origin="https://app.example.test",
            office_origin="https://app.example.test",
            office_secret="synthetic-signing-secret-32-characters",
        )
