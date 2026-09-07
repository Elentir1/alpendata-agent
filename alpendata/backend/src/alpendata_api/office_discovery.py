"""Resolve editor actions from the configured Collabora server, never a user URL."""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from xml.etree.ElementTree import ParseError

import requests
from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import fromstring
from fastapi import HTTPException


def editor_action(origin, extension, language, wopi_url):
    try:
        with requests.Session() as transport:
            transport.trust_env = False
            with transport.get(
                origin + "/hosting/discovery", timeout=(5, 15), allow_redirects=False, stream=True
            ) as response:
                response.raise_for_status()
                if response.status_code != 200:
                    raise ValueError("Unexpected discovery response")
                data = bytearray()
                for chunk in response.iter_content(65536):
                    data.extend(chunk)
                    if len(data) > 1024 * 1024:
                        raise ValueError("Discovery too large")
        tree = fromstring(bytes(data))
        action = next(
            (
                node
                for node in tree.iter("action")
                if node.get("ext") == extension and node.get("name") == "edit"
            ),
            None,
        )
        if action is None:
            raise ValueError("Unsupported editor format")
        url = urlsplit(action.get("urlsrc", ""))
        if (
            url.scheme + "://" + url.netloc != origin
            or url.username
            or url.password
            or url.fragment
            or not url.path.startswith("/browser/")
        ):
            raise ValueError("Untrusted editor action")
        # Discovery may contain optional WOPI placeholders; unprovided ones must be removed.
        query = [
            (key, value)
            for key, value in parse_qsl(url.query)
            if "<" not in key + value and key not in {"WOPISrc", "lang", "access_token"}
        ]
        query.extend((("WOPISrc", wopi_url), ("lang", language)))
        return urlunsplit((url.scheme, url.netloc, url.path, urlencode(query), ""))
    except (requests.RequestException, ValueError, DefusedXmlException, ParseError) as error:
        raise HTTPException(503, "document_editor_unavailable") from error
