"""Private download receipts survive interruption; owners never share access."""

import base64
import hashlib
import io
import zipfile
from uuid import uuid4

import pytest
from fastapi import HTTPException
from test_routines import connected_service as connected_service
from test_routines import routine_service as routine_service

from alpendata_api.artifacts import MAX_BYTES, validate_document
from alpendata_api.chat_worker import ChatWorker
from alpendata_api.models import Conversation, Membership
from alpendata_api.runtime import RuntimeFailure


def example_pdf():
    # A complete one-page PDF fixture, including offsets and a real text stream.
    stream = b"BT /F1 18 Tf 72 740 Td (Coaching session) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    content = b"%PDF-1.4\n"
    offsets = []
    for index, obj in enumerate(objects, 1):
        offsets.append(len(content))
        content += str(index).encode() + b" 0 obj\n" + obj + b"\nendobj\n"
    xref = len(content)
    content += b"xref\n0 6\n0000000000 65535 f \n"
    content += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    return content + f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()


def start_document_turn(service):
    app, client, settings, _, _, org, _, bob = service
    base = f"/api/organizations/{org}"
    assert (
        client.put(
            base + "/onboarding",
            headers=bob[2],
            json={
                "language": "en",
                "role": "Coach",
                "needs": "Session documents",
            },
        ).status_code
        == 200
    )
    conversation = client.post(base + "/chat/conversations", headers=bob[2], json={"language": "en"}).json()
    path = base + "/chat/conversations/" + conversation["id"]
    assert (
        client.post(
            path + "/turns",
            headers=bob[2],
            json={
                "request_id": str(uuid4()),
                "message": "Create my session document",
            },
        ).status_code
        == 202
    )
    return path


def test_documents_are_private_immutable_and_bound_to_a_live_conversation(routine_service):
    app, client, settings, _, _, org, alice, bob = routine_service
    path = start_document_turn(routine_service)
    worker = ChatWorker(settings, app.state.session_factory, runtime=object())
    job = worker.claim()
    content = example_pdf()
    payload = {
        "kind": "document",
        "filename": "Séance.pdf",
        "content_base64": base64.b64encode(content).decode(),
    }
    reply = worker.tool(job, [], payload)
    assert reply["status"] == 200, reply
    assert worker.tool(job, [], payload) == reply
    assert reply["body"]["sha256"] == hashlib.sha256(content).hexdigest()
    document = f"/api/organizations/{org}/documents/{reply['body']['id']}/download"
    response = client.get(document, headers=bob[2])
    assert response.content == content
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == "attachment; filename*=UTF-8''S%C3%A9ance.pdf"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert client.get(document, headers=alice[2]).status_code == 404
    assert client.get(document).status_code == 401
    assert client.get(document.replace(org, str(uuid4())), headers=bob[2]).status_code == 404
    assert worker.tool(job, [], {**payload, "owner_id": alice[0]})["status"] == 400
    assert worker.tool(job, [], {**payload, "filename": "../other.pdf"})["status"] == 400
    assert worker.tool(job, [], {**payload, "filename": "fake.docx"})["status"] == 400
    assert worker.tool(job, [], {**payload, "content_base64": "!!!"})["status"] == 400
    # A legacy conversation cannot silently gain a new tool mid-history.
    with app.state.session_factory.begin() as db:
        db.get(Conversation, path.rsplit("/", 1)[1]).documents_enabled = False
    assert worker.tool(job, [], payload)["status"] == 403
    with app.state.session_factory.begin() as db:
        db.get(Conversation, path.rsplit("/", 1)[1]).documents_enabled = True
    worker.finish(job, error="agent_worker_interrupted")
    with pytest.raises(RuntimeFailure, match="agent_lease_lost"):
        worker.tool(job, [], payload)
    detail = client.get(path, headers=bob[2]).json()
    assert detail["turns"][0]["artifacts"] == [reply["body"]]
    assert "content_base64" not in reply["body"]
    attachment = client.post(
        path + "/files/from-artifact", headers=bob[2], json={"artifact_id": reply["body"]["id"]}
    )
    assert attachment.status_code == 201, attachment.text
    assert (
        client.post(
            path + "/files/from-artifact", headers=bob[2], json={"artifact_id": reply["body"]["id"]}
        ).json()["id"]
        == attachment.json()["id"]
    )
    assert len(client.get(path + "/files", headers=bob[2]).json()["files"]) == 1
    assert (
        client.post(
            path + "/files/from-artifact", headers=alice[2], json={"artifact_id": reply["body"]["id"]}
        ).status_code
        == 404
    )
    with app.state.session_factory.begin() as db:
        db.get(Membership, (org, bob[0])).licensed = False
    assert client.get(document, headers=bob[2]).content == content
    with app.state.session_factory.begin() as db:
        db.get(Membership, (org, bob[0])).active = False
    assert client.get(document, headers=bob[2]).status_code == 404


def test_office_containers_require_matching_content_types_and_bounded_contents():
    # Deliberately minimal packages exercise container validation, not Office layout.
    formats = {
        "docx": ("word/document.xml", "wordprocessingml.document"),
        "xlsx": ("xl/workbook.xml", "spreadsheetml.sheet"),
        "pptx": ("ppt/presentation.xml", "presentationml.presentation"),
    }
    for extension, (main, kind) in formats.items():
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as package:
            package.writestr(main, "<document />")
            package.writestr(
                "[Content_Types].xml",
                (
                    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                    f'<Override PartName="/{main}" '
                    'ContentType="application/vnd.openxmlformats-officedocument.'
                    f'{kind}.main+xml" /></Types>'
                ),
            )
        content = stream.getvalue()
        assert validate_document("Session." + extension, content).endswith(kind)
        wrong = "xlsx" if extension == "docx" else "docx"
        with pytest.raises(HTTPException) as error:
            validate_document("Session." + wrong, content)
        assert error.value.detail == "document_format_invalid"
        with zipfile.ZipFile(stream, "a") as package:
            package.writestr("../outside.txt", "Not allowed")
        with pytest.raises(HTTPException):
            validate_document("Session." + extension, stream.getvalue())
    with pytest.raises(HTTPException) as error:
        validate_document("Session.pdf", b"%PDF-" + b"x" * MAX_BYTES + b"%%EOF")
    assert error.value.status_code == 413
