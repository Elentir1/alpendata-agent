"""Search excerpts are built only from rows the requesting member can currently read."""

from fastapi import Query, Request
from sqlalchemy import or_, select

from .file_access import unpublished_file
from .models import ChatTurn, FileVersion, Project, ProjectEntry, ProjectFile, WorkspaceFile
from .project_access import accessible_projects


def excerpt(text, term, limit=260):
    text = " ".join((text or "").split())
    position = text.lower().find(term.lower())
    start = max(0, position - 70)
    return ("…" if start else "") + text[start : start + limit] + ("…" if len(text) > start + limit else "")


def conversation_match(db, item, term):
    if term.lower() in item.title.lower():
        return {"kind": "title", "text": excerpt(item.title, term)}
    turn = db.scalar(
        select(ChatTurn)
        .where(
            ChatTurn.conversation_id == item.id,
            or_(
                ChatTurn.message.icontains(term, autoescape=True),
                ChatTurn.response.icontains(term, autoescape=True),
            ),
        )
        .order_by(ChatTurn.sequence.desc())
        .limit(1)
    )
    if turn:
        text = turn.message if term.lower() in turn.message.lower() else turn.response
        return {"kind": "message", "sequence": turn.sequence, "text": excerpt(text, term)}
    row = db.execute(
        select(WorkspaceFile.filename, FileVersion.analysis_text)
        .join(FileVersion, FileVersion.file_id == WorkspaceFile.id)
        .where(
            WorkspaceFile.conversation_id == item.id,
            unpublished_file(),
            FileVersion.version == WorkspaceFile.version,
            or_(
                WorkspaceFile.filename.icontains(term, autoescape=True),
                FileVersion.analysis_text.icontains(term, autoescape=True),
            ),
        )
        .order_by(WorkspaceFile.created_at.desc())
        .limit(1)
    ).first()
    return (
        {
            "kind": "document",
            "filename": row.filename,
            "text": excerpt(row.analysis_text or row.filename, term),
        }
        if row
        else None
    )


def attach_search_routes(router, factory, actor):
    @router.get("/api/organizations/{organization_id}/chat/search-resources")
    def resources(
        organization_id: str,
        request: Request,
        q: str = Query(min_length=1, max_length=160),
        before: int = Query(default=0, ge=0),
        project: str | None = None,
    ):
        term = q.strip()
        if not term:
            return {"results": [], "next_offset": None}
        with factory.begin() as db:
            user = actor(db, request, organization_id, licensed=False)
            projects = select(Project.id).where(
                Project.organization_id == organization_id, accessible_projects(user.id)
            )
            if project:
                projects = projects.where(Project.id == project)
            files = db.execute(
                select(
                    WorkspaceFile.id,
                    WorkspaceFile.filename,
                    WorkspaceFile.version,
                    FileVersion.analysis_text,
                    Project.id.label("project_id"),
                    Project.name.label("project_name"),
                )
                .join(ProjectFile, ProjectFile.file_id == WorkspaceFile.id)
                .join(Project, Project.id == ProjectFile.project_id)
                .join(FileVersion, FileVersion.file_id == WorkspaceFile.id)
                .where(
                    Project.id.in_(projects),
                    WorkspaceFile.organization_id == organization_id,
                    FileVersion.version == WorkspaceFile.version,
                    or_(
                        WorkspaceFile.filename.icontains(term, autoescape=True),
                        FileVersion.analysis_text.icontains(term, autoescape=True),
                    ),
                )
                .order_by(WorkspaceFile.id)
                .offset(before)
                .limit(21)
            ).all()
            entries = db.execute(
                select(ProjectEntry, Project.name)
                .join(Project, Project.id == ProjectEntry.project_id)
                .where(
                    ProjectEntry.organization_id == organization_id,
                    Project.id.in_(projects),
                    or_(
                        ProjectEntry.title.icontains(term, autoescape=True),
                        ProjectEntry.content.icontains(term, autoescape=True),
                    ),
                )
                .order_by(ProjectEntry.id)
                .offset(before)
                .limit(21)
            ).all()
            return {
                "results": [
                    {
                        "kind": "document",
                        "id": row.id,
                        "title": row.filename,
                        "version": row.version,
                        "project_id": row.project_id,
                        "project_name": row.project_name,
                        "text": excerpt(row.analysis_text or row.filename, term),
                    }
                    for row in files[:20]
                ]
                + [
                    {
                        "kind": "knowledge",
                        "id": entry.id,
                        "title": entry.title,
                        "project_id": entry.project_id,
                        "project_name": name,
                        "text": excerpt(entry.content, term),
                    }
                    for entry, name in entries[:20]
                ],
                "next_offset": before + 20 if len(files) > 20 or len(entries) > 20 else None,
            }
