"""Explicit company copies with independent ACLs; personal connections never transfer."""

import base64
import binascii
import hashlib
import json
from typing import Literal
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import Field, model_validator
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import defer

from .access import lock_organization, member, owned
from .artifacts import OWNER_BYTES, ArtifactInput, validate_document
from .auth import authenticate, request_authorization
from .connections import lock_member
from .models import Artifact, CompanyResource, CompanyResourceGrant, Membership, User, now
from .schemas import Input


class Publication(Input):
    title: str = Field(min_length=1, max_length=160)
    kind: Literal["note", "document"]
    audience: Literal["team", "selected"]
    member_ids: list[UUID] = Field(default_factory=list, max_length=1000)
    text: str = Field(default="", max_length=20000)
    document: ArtifactInput | None = None
    source_document_id: UUID | None = None
    confirmed: Literal[True]

    @model_validator(mode="after")
    def content_matches(self):
        if self.kind == "note" and (not self.text or self.document is not None or self.source_document_id):
            raise ValueError("A note requires text only")
        if self.kind == "document" and (
            self.text or (self.document is None) == (self.source_document_id is None)
        ):
            raise ValueError("A document requires exactly one uploaded file or personal document")
        if self.audience == "team" and self.member_ids:
            raise ValueError("Team access does not use individual grants")
        return self


class ResourceCreate(Publication):
    request_id: UUID


class ResourceUpdate(Publication):
    version: int = Field(ge=1)


class ResourceAccess(Input):
    version: int = Field(ge=1)
    audience: Literal["team", "selected"]
    member_ids: list[UUID] = Field(default_factory=list, max_length=1000)
    confirmed: Literal[True]

    @model_validator(mode="after")
    def explicit_audience(self):
        if self.audience == "team" and self.member_ids:
            raise ValueError("Team access does not use individual grants")
        return self


class ResourceVersion(Input):
    version: int = Field(ge=1)


def can_manage(row, membership):
    return membership.role == "admin" or row.created_by == membership.user_id


def resource_scope(organization_id, membership):
    scope = [CompanyResource.organization_id == organization_id, CompanyResource.active.is_(True)]
    if membership.role != "admin":
        grant = (
            select(CompanyResourceGrant.resource_id)
            .where(
                CompanyResourceGrant.resource_id == CompanyResource.id,
                CompanyResourceGrant.organization_id == organization_id,
                CompanyResourceGrant.user_id == membership.user_id,
            )
            .exists()
        )
        scope.append(
            or_(CompanyResource.created_by == membership.user_id, CompanyResource.audience == "team", grant)
        )
    return scope


def visible_resource(db, organization_id, membership, resource_id, version=None, *, manage=False):
    row = db.scalar(
        select(CompanyResource).where(
            *resource_scope(organization_id, membership), CompanyResource.id == resource_id
        )
    )
    if row is None or (manage and not can_manage(row, membership)):
        raise HTTPException(404, "company_resource_not_found")
    if version is not None and row.version != version:
        raise HTTPException(409, "company_resource_changed")
    return row


def resource_view(db, row, *, manager=False, include_text=False):
    result = {
        key: getattr(row, key)
        for key in (
            "id",
            "created_by",
            "title",
            "kind",
            "filename",
            "media_type",
            "size",
            "sha256",
            "version",
            "created_at",
            "updated_at",
        )
    }
    if include_text and row.kind == "note":
        result["text"] = row.text
    result["can_manage"] = manager
    if manager:
        result["audience"] = row.audience
        result["member_ids"] = sorted(
            db.scalars(
                select(CompanyResourceGrant.user_id).where(CompanyResourceGrant.resource_id == row.id)
            ).all()
        )
    return result


def resource_list(db, organization_id, membership, *, query="", before=0):
    statement = (
        select(CompanyResource)
        .options(defer(CompanyResource.content), defer(CompanyResource.text))
        .where(*resource_scope(organization_id, membership))
    )
    if query:
        statement = statement.where(
            CompanyResource.title.ilike(
                "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%", escape="\\"
            )
        )
    rows = db.scalars(
        statement.order_by(CompanyResource.created_at.desc(), CompanyResource.id).offset(before).limit(51)
    ).all()
    return {
        "resources": [resource_view(db, row, manager=can_manage(row, membership)) for row in rows[:50]],
        "next_offset": before + 50 if len(rows) > 50 else None,
    }


def apply_grants(db, organization_id, row, body):
    grants = sorted({str(identifier) for identifier in body.member_ids})
    valid = set(
        db.scalars(
            select(Membership.user_id).where(
                Membership.organization_id == organization_id,
                Membership.active.is_(True),
                Membership.user_id.in_(grants),
            )
        ).all()
    )
    if valid != set(grants):
        raise HTTPException(422, "company_resource_members_invalid")
    row.audience = body.audience
    db.execute(delete(CompanyResourceGrant).where(CompanyResourceGrant.resource_id == row.id))
    db.flush()
    db.add_all(
        [
            CompanyResourceGrant(resource_id=row.id, organization_id=organization_id, user_id=uid)
            for uid in grants
        ]
    )
    db.flush()


def apply_publication(db, organization_id, row, body, user_id):
    content, media_type, filename, digest = None, None, None, None
    if body.document is not None:
        try:
            content = base64.b64decode(body.document.content_base64, validate=True)
        except (ValueError, binascii.Error):
            raise HTTPException(400, "document_format_invalid") from None
        filename = body.document.filename
        media_type = validate_document(filename, content)
        digest = hashlib.sha256(content).hexdigest()
    if body.source_document_id is not None:
        original = owned(db, Artifact, organization_id, user_id, str(body.source_document_id))
        content, media_type, filename, digest = (
            original.content,
            original.media_type,
            original.filename,
            original.sha256,
        )
    used = db.scalar(
        select(func.coalesce(func.sum(CompanyResource.size), 0)).where(
            CompanyResource.organization_id == organization_id, CompanyResource.id != row.id
        )
    )
    if used + len(content or b"") > OWNER_BYTES:
        raise HTTPException(409, "company_resource_storage_full")
    row.title, row.kind, row.audience, row.text = body.title, body.kind, body.audience, body.text
    row.filename, row.media_type, row.content, row.sha256 = filename, media_type, content, digest
    row.size, row.updated_at = len(content or b""), now()
    apply_grants(db, organization_id, row, body)


def company_resources_router(settings, factory):
    router = APIRouter()
    base = "/api/organizations/{organization_id}/company-resources"

    def actor(db, request, organization_id, *, write=False):
        user = authenticate(db, request_authorization(request, settings))
        if write:
            lock_organization(db, organization_id)
            membership = member(db, user, organization_id, licensed=False)
            # Match company-policy lock order. A revocation waits for current reads,
            # and waiting brokers see the committed audience on their next read.
            db.scalars(
                select(Membership)
                .where(Membership.organization_id == organization_id)
                .order_by(Membership.user_id)
                .with_for_update()
            ).all()
        else:
            membership = lock_member(db, user, organization_id, licensed=False)
        return user, membership

    @router.get(base)
    def listing(
        organization_id: str,
        request: Request,
        query: str = Query(default="", max_length=160),
        before: int = Query(default=0, ge=0),
    ):
        with factory.begin() as db:
            _, membership = actor(db, request, organization_id)
            return resource_list(db, organization_id, membership, query=query, before=before)

    @router.post(base, status_code=201)
    def create(organization_id: str, request: Request, body: ResourceCreate):
        with factory.begin() as db:
            user, _ = actor(db, request, organization_id, write=True)
            digest = hashlib.sha256(
                json.dumps(
                    body.model_dump(
                        mode="json",
                        exclude={"source_document_id"} if body.source_document_id is None else set(),
                    ),
                    sort_keys=True,
                ).encode()
            ).hexdigest()
            row = db.scalar(
                select(CompanyResource).where(
                    CompanyResource.organization_id == organization_id,
                    CompanyResource.created_by == user.id,
                    CompanyResource.request_id == str(body.request_id),
                )
            )
            if row is not None:
                if row.request_hash != digest or not row.active:
                    raise HTTPException(409, "company_resource_request_changed")
                return resource_view(db, row, manager=True, include_text=True)
            count = db.scalar(
                select(func.count())
                .select_from(CompanyResource)
                .where(CompanyResource.organization_id == organization_id, CompanyResource.active.is_(True))
            )
            if count >= 200:
                raise HTTPException(409, "company_resource_storage_full")
            row = CompanyResource(
                organization_id=organization_id,
                created_by=user.id,
                request_id=str(body.request_id),
                request_hash=digest,
                title=body.title,
                kind=body.kind,
                audience=body.audience,
            )
            db.add(row)
            db.flush()
            apply_publication(db, organization_id, row, body, user.id)
            return resource_view(db, row, manager=True, include_text=True)

    @router.get(base + "/recipients")
    def recipients(organization_id: str, request: Request):
        with factory.begin() as db:
            user, _ = actor(db, request, organization_id)
            rows = db.execute(
                select(Membership.user_id, User.display_name, Membership.role)
                .join(User)
                .where(
                    Membership.organization_id == organization_id,
                    Membership.active.is_(True),
                    User.active.is_(True),
                )
                .order_by(User.display_name, Membership.user_id)
            ).all()
            # A sharing picker needs names, not administrative licence or invitation data.
            return {
                "current_user_id": user.id,
                "members": [
                    {"user_id": uid, "display_name": name, "role": role, "active": True}
                    for uid, name, role in rows
                ],
            }

    @router.get(base + "/{resource_id}")
    def read(organization_id: str, resource_id: str, request: Request):
        with factory.begin() as db:
            _, membership = actor(db, request, organization_id)
            row = visible_resource(db, organization_id, membership, resource_id)
            return resource_view(db, row, manager=can_manage(row, membership), include_text=True)

    @router.put(base + "/{resource_id}")
    def update(organization_id: str, resource_id: str, request: Request, body: ResourceUpdate):
        with factory.begin() as db:
            user, membership = actor(db, request, organization_id, write=True)
            row = visible_resource(db, organization_id, membership, resource_id, body.version, manage=True)
            apply_publication(db, organization_id, row, body, user.id)
            row.version += 1
            return resource_view(db, row, manager=True, include_text=True)

    @router.patch(base + "/{resource_id}/access")
    def access(organization_id: str, resource_id: str, request: Request, body: ResourceAccess):
        with factory.begin() as db:
            _, membership = actor(db, request, organization_id, write=True)
            row = visible_resource(db, organization_id, membership, resource_id, body.version, manage=True)
            apply_grants(db, organization_id, row, body)
            row.version, row.updated_at = row.version + 1, now()
            return resource_view(db, row, manager=True, include_text=True)

    @router.delete(base + "/{resource_id}", status_code=204)
    def remove(organization_id: str, resource_id: str, request: Request, body: ResourceVersion):
        with factory.begin() as db:
            _, membership = actor(db, request, organization_id, write=True)
            row = visible_resource(db, organization_id, membership, resource_id, body.version, manage=True)
            row.active, row.text, row.content, row.size = False, "", None, 0
            row.version, row.updated_at = row.version + 1, now()
            db.execute(delete(CompanyResourceGrant).where(CompanyResourceGrant.resource_id == row.id))

    @router.get(base + "/{resource_id}/download")
    def download(organization_id: str, resource_id: str, request: Request, version: int = Query(ge=1)):
        with factory.begin() as db:
            _, membership = actor(db, request, organization_id)
            row = visible_resource(db, organization_id, membership, resource_id, version)
            if row.kind != "document":
                raise HTTPException(400, "company_resource_not_document")
            return Response(
                content=row.content,
                media_type=row.media_type,
                headers={
                    "Content-Disposition": "attachment; filename*=UTF-8''" + quote(row.filename, safe=""),
                    "Content-Security-Policy": "sandbox; default-src 'none'",
                },
            )

    return router
