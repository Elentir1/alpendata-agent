"""Bounded comparison of extracted content, with exact immutable version references."""

from fastapi import HTTPException, Request
from pydantic import Field

from .file_access import file_access
from .schemas import Input


class CompareInput(Input):
    before_version: int = Field(ge=1)
    after_version: int = Field(ge=1)
    other_file_id: str | None = Field(default=None, min_length=36, max_length=36)


def attach_comparison_route(router, factory, actor):
    from .workspace_files import version_record

    @router.post("/api/organizations/{organization_id}/files/{file_id}/compare")
    def compare(organization_id: str, file_id: str, request: Request, body: CompareInput):
        with factory() as db:
            user = actor(db, request, organization_id)
            left = file_access(db, organization_id, user.id, file_id)
            right = (
                file_access(db, organization_id, user.id, body.other_file_id) if body.other_file_id else left
            )
            before, after = (
                version_record(db, left, body.before_version),
                version_record(db, right, body.after_version),
            )
            if any(row.analysis_status in ("queued", "running") for row in (before, after)):
                raise HTTPException(409, "document_analysis_pending")
            left_pages = {page["reference"]: page["text"] for page in before.analysis_pages or []}
            right_pages = {page["reference"]: page["text"] for page in after.analysis_pages or []}
            references = dict.fromkeys([*left_pages, *right_pages])
            changed = [
                reference
                for reference in references
                if left_pages.get(reference) != right_pages.get(reference)
            ]
            partial = len(changed) > 20 or any(row.analysis_status == "partial" for row in (before, after))
            differences = []
            for reference in changed[:20]:
                old, new = left_pages.get(reference, ""), right_pages.get(reference, "")
                partial = partial or max(len(old), len(new)) > 4000
                differences.append({"reference": reference, "before": old[:4000], "after": new[:4000]})
            return {
                "before": {"file_id": left.id, "version": before.version, "status": before.analysis_status},
                "after": {"file_id": right.id, "version": after.version, "status": after.analysis_status},
                "identical_bytes": before.sha256 == after.sha256,
                "changed_sections": len(changed),
                "partial": partial,
                "differences": differences,
                "text_available": bool(left_pages or right_pages),
            }
