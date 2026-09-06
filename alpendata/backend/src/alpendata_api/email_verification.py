"""Locate correlated sent copies without interpreting absence as non-delivery."""

from collections import Counter
from datetime import datetime, timezone

from fastapi import HTTPException

from .access import owned
from .email_drafts import attempt_view, draft_view
from .graph import items, web_link
from .graph_email import CORRELATION_HEADER
from .models import EmailAttempt, EmailDraft, now


def recipients_match(candidate, message):
    for key in ("to", "cc", "bcc"):
        values = candidate.get(key + "Recipients", [])
        if not isinstance(values, list) or len(values) > 20:
            return False
        addresses = []
        for value in values:
            address = value.get("emailAddress") if isinstance(value, dict) else None
            address = address.get("address") if isinstance(address, dict) else None
            if not isinstance(address, str):
                return False
            addresses.append(address.casefold())
        if Counter(addresses) != Counter(address.casefold() for address in message[key]):
            return False
    return True


def sent_copy(candidate, attempt):
    headers = candidate.get("internetMessageHeaders")
    if not isinstance(headers, list):
        return None
    markers = [
        header.get("value")
        for header in headers
        if isinstance(header, dict) and str(header.get("name", "")).casefold() == CORRELATION_HEADER
    ]
    if markers != [attempt.correlation_id]:
        return None
    if candidate.get("isDraft") is not False or candidate.get("subject") != attempt.message["subject"]:
        return None
    if not recipients_match(candidate, attempt.message):
        return None
    identifier, sent_at = candidate.get("id"), candidate.get("sentDateTime")
    if not isinstance(identifier, str) or not 1 <= len(identifier) <= 2048 or not isinstance(sent_at, str):
        return None
    try:
        instant = datetime.fromisoformat(sent_at.replace("Z", "+00:00"))
        if instant.tzinfo is None or not attempt.created_at - 300 <= instant.timestamp() <= now() + 300:
            return None
    except ValueError:
        return None
    return {"item_id": identifier, "sent_at": sent_at, "url": web_link(candidate.get("webLink"))}


def find_sent_copy(graph, token, attempt):
    since = datetime.fromtimestamp(attempt.created_at - 300, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    data = graph.request(
        token,
        "GET",
        "/me/mailFolders/sentitems/messages",
        params={
            "$filter": "sentDateTime ge " + since,
            "$orderby": "sentDateTime desc",
            "$top": 100,
            "$select": (
                "id,subject,toRecipients,ccRecipients,bccRecipients,isDraft,"
                "internetMessageHeaders,sentDateTime,webLink"
            ),
        },
    )
    candidates = items(data.get("value"), 100)
    matches = [copy for candidate in candidates if (copy := sent_copy(candidate, attempt))]
    # The response's nextLink is never followed. The visible bound prevents an
    # absent result in this selection from being interpreted as permission to retry.
    return {
        "checked_at": now(),
        "status": "found" if matches else "not_found",
        "searched": len(candidates),
        "partial": bool(data.get("@odata.nextLink")) or len(data["value"]) > 100,
        "match_count": len(matches),
        "copy": matches[0] if matches else None,
    }


def verify_attempt(factory, microsoft, actor, request, organization_id, draft_id, attempt_id):
    with factory.begin() as db:
        user = actor(db, request, organization_id)
        draft = owned(db, EmailDraft, organization_id, user.id, draft_id)
        attempt = owned(db, EmailAttempt, organization_id, user.id, attempt_id)
        if attempt.draft_id != draft_id:
            raise HTTPException(404, "resource_not_found")
        if attempt.verification and attempt.verification.get("status") == "found":
            return draft_view(db, draft)
        if not attempt_view(attempt)["can_verify"]:
            raise HTTPException(409, "email_verification_unavailable")
        db.expunge(attempt)
    result = microsoft.execute(
        organization_id,
        lambda db: actor(db, request, organization_id),
        "mail",
        lambda graph, token: find_sent_copy(graph, token, attempt),
    )
    with factory.begin() as db:
        user = actor(db, request, organization_id)
        current = owned(db, EmailAttempt, organization_id, user.id, attempt_id)
        # A second check that started earlier cannot erase a positive observation.
        if not current.verification or current.verification.get("status") != "found":
            current.verification = result
        db.flush()
        return draft_view(db, owned(db, EmailDraft, organization_id, user.id, draft_id))
