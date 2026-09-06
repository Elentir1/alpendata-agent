"""Fixed Graph destinations and single-attempt writes of reviewed document bytes."""

import json
from contextlib import nullcontext
from urllib.parse import quote

import requests

from .graph import GraphError, items, object_value, web_link
from .graph_documents import FileInput, download_url


def item_path(drive_id, item_id):
    data = FileInput(drive_id=drive_id, item_id=item_id)
    return f"/drives/{quote(data.drive_id, safe='')}/items/{quote(data.item_id, safe='')}"


def folder_view(data, drive_id=None):
    if not isinstance(data.get("folder"), dict):
        raise GraphError(400, "sharepoint_folder_required")
    identity = FileInput(
        drive_id=drive_id or object_value(data.get("parentReference")).get("driveId"),
        item_id=data.get("id"),
    )
    name = data.get("name")
    if not isinstance(name, str) or not 1 <= len(name) <= 1024:
        raise GraphError(502, "microsoft_read_failed")
    return {
        "drive_id": identity.drive_id,
        "item_id": identity.item_id,
        "name": name,
        "url": web_link(data.get("webUrl")),
    }


def get_folder(graph, token, drive_id, item_id):
    return folder_view(graph.request(token, "GET", item_path(drive_id, item_id)), drive_id)


def search_folders(graph, token, query):
    # Resolve search hits to their containing folder. This includes libraries
    # shared with the user, without adding site-wide discovery permissions.
    hits = graph.files(token, query)["files"]
    folders = {}
    for hit in hits:
        try:
            data = graph.request(token, "GET", item_path(hit["drive_id"], hit["id"]))
            if isinstance(data.get("folder"), dict):
                folder = folder_view(data, hit["drive_id"])
            else:
                parent = object_value(data.get("parentReference"))
                folder = get_folder(graph, token, parent.get("driveId"), parent.get("id"))
            folders[(folder["drive_id"], folder["item_id"])] = folder
        except GraphError as error:
            if error.status not in (403, 404):
                raise
    return {"folders": list(folders.values())}


def browse_folder(graph, token, drive_id, item_id):
    path = item_path(drive_id, item_id)
    folder = get_folder(graph, token, drive_id, item_id)
    data = graph.request(
        token,
        "GET",
        path + "/children",
        params={
            "$top": 200,
            "$select": "id,name,folder,parentReference,webUrl",
            "$orderby": "name",
        },
    )
    return {
        "folder": folder,
        "folders": [
            folder_view(item, drive_id)
            for item in items(data.get("value", []), 200)
            if isinstance(item.get("folder"), dict)
        ],
        "partial": bool(data.get("@odata.nextLink")),
    }


def inspect_destination(graph, token, drive_id, folder_id, filename):
    folder = get_folder(graph, token, drive_id, folder_id)
    try:
        existing = graph.request(
            token, "GET", item_path(drive_id, folder_id) + ":/" + quote(filename, safe="")
        )
    except GraphError as error:
        if error.status != 404:
            raise
        existing = None
    if existing is not None:
        FileInput(drive_id=drive_id, item_id=existing.get("id"))
        if not isinstance(existing.get("file"), dict):
            raise GraphError(409, "sharepoint_name_is_folder")
        if not isinstance(existing.get("eTag"), str) or not 1 <= len(existing["eTag"]) <= 1024:
            raise GraphError(502, "microsoft_read_failed")
    return folder, existing


def write_request(transport, method, url, *, headers, content=None, body=None, credentialed=True):
    """After dispatch, absent or malformed success evidence is an unknown outcome."""
    try:
        transport.trust_env = False
        with transport.request(
            method,
            url,
            headers=headers,
            data=content,
            json=body,
            timeout=20,
            allow_redirects=False,
            stream=True,
        ) as response:
            failures = {
                400: "sharepoint_save_rejected",
                401: "microsoft_reconnect_required" if credentialed else "sharepoint_upload_expired",
                403: "microsoft_access_denied",
                404: "microsoft_item_not_found",
                409: "sharepoint_destination_changed",
                412: "sharepoint_destination_changed",
                423: "sharepoint_file_locked",
                429: "microsoft_rate_limited",
                507: "sharepoint_storage_full",
            }
            if response.status_code in failures:
                raise GraphError(response.status_code, failures[response.status_code])
            if response.status_code not in (200, 201):
                raise GraphError(502, "sharepoint_save_unknown")
            content = bytearray()
            for chunk in response.iter_content(65536):
                content.extend(chunk)
                if len(content) > 2 * 1024 * 1024:
                    raise GraphError(502, "sharepoint_save_unknown")
            result = json.loads(content)
            if not isinstance(result, dict):
                raise ValueError("Invalid response")
            return result
    except (requests.RequestException, ValueError):
        raise GraphError(502, "sharepoint_save_unknown") from None


def save_document(graph, token, review, content, media_type):
    folder, existing = inspect_destination(graph, token, review.drive_id, review.folder_id, review.filename)
    if (folder["name"], folder["url"]) != (review.folder_name, review.folder_url):
        raise GraphError(409, "sharepoint_destination_changed")
    actual = (existing.get("id"), existing.get("eTag")) if existing else (None, None)
    if actual != (review.existing_id, review.existing_etag):
        raise GraphError(409, "sharepoint_destination_changed")
    headers = {"Authorization": "Bearer " + token, "Content-Type": media_type}
    with nullcontext(graph.session) if graph.session is not None else requests.Session() as transport:
        if review.existing_id:
            headers["If-Match"] = review.existing_etag
            result = write_request(
                transport,
                "PUT",
                "https://graph.microsoft.com/v1.0"
                + item_path(review.drive_id, review.existing_id)
                + "/content",
                headers=headers,
                content=content,
            )
        else:
            # A session's fail behavior is checked again at completion if a
            # competing upload creates the same name after the preview.
            path = item_path(review.drive_id, review.folder_id) + ":/" + quote(review.filename, safe="")
            session = write_request(
                transport,
                "POST",
                "https://graph.microsoft.com/v1.0" + path + ":/createUploadSession",
                headers={"Authorization": "Bearer " + token},
                body={"item": {"name": review.filename, "@microsoft.graph.conflictBehavior": "fail"}},
            )
            url = download_url(session.get("uploadUrl"))
            with (
                nullcontext(graph.content_session)
                if graph.content_session is not None
                else requests.Session() as upload
            ):
                result = write_request(
                    upload,
                    "PUT",
                    url,
                    content=content,
                    credentialed=False,
                    headers={
                        "Content-Type": media_type,
                        "Content-Length": str(len(content)),
                        "Content-Range": f"bytes 0-{len(content) - 1}/{len(content)}",
                    },
                )
    if (
        not isinstance(result.get("id"), str)
        or not result["id"]
        or len(result["id"]) > 512
        or result.get("name") != review.filename
        or result.get("size") != len(content)
        or not isinstance(result.get("file"), dict)
        or (review.existing_id and result["id"] != review.existing_id)
    ):
        raise GraphError(502, "sharepoint_save_unknown")
    return {
        "item_id": result["id"],
        "name": result["name"],
        "size": result["size"],
        "url": web_link(result.get("webUrl")),
    }
