"""One non-retried send from the authenticated user's own mailbox."""

import base64
from contextlib import nullcontext

import requests

from .graph import GraphError

CORRELATION_HEADER = "x-alpendata-message-id"


def send_email(graph, token, message, files, correlation_id):
    payload = {
        "subject": message["subject"],
        "body": {"contentType": "Text", "content": message["body"]},
        "internetMessageHeaders": [{"name": CORRELATION_HEADER, "value": correlation_id}],
        **{
            key + "Recipients": [{"emailAddress": {"address": address}} for address in message[key]]
            for key in ("to", "cc", "bcc")
        },
        "attachments": [
            {
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": name,
                "contentType": media_type,
                "contentBytes": base64.b64encode(content).decode("ascii"),
            }
            for name, media_type, content in files
        ],
    }
    try:
        with nullcontext(graph.session) if graph.session is not None else requests.Session() as transport:
            transport.trust_env = False
            with transport.request(
                "POST",
                "https://graph.microsoft.com/v1.0/me/sendMail",
                json={"message": payload},
                headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
                timeout=20,
                allow_redirects=False,
                stream=True,
            ) as response:
                if response.status_code == 202:
                    return
                if response.status_code == 401:
                    raise GraphError(409, "microsoft_reconnect_required")
                if response.status_code == 403:
                    raise GraphError(403, "microsoft_access_denied")
                if response.status_code in (400, 404, 405, 413, 415, 422, 429):
                    raise GraphError(409, "email_send_rejected")
                # A timeout or an unexpected response cannot establish non-delivery.
                raise GraphError(502, "email_send_unknown")
    except requests.RequestException:
        raise GraphError(502, "email_send_unknown") from None
