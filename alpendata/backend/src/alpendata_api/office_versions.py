"""Session snapshots and conflict copies shared by WOPI reads and saves."""

import hashlib

from .file_access import file_access, publication
from .models import ProjectFile, WorkspaceFile
from .workspace_files import add_version, file_store, version_record


def snapshot(db, session, original, write=False):
    if session.conflict_file_id:
        item = file_access(
            db,
            original.organization_id,
            session.editor_id or session.owner_id,
            session.conflict_file_id,
            write=write,
        )
        return item, session.conflict_version
    return original, session.saved_version or session.base_version


def save_snapshot(db, settings, session, original, data):
    item, expected = snapshot(db, session, original, write=True)
    digest = hashlib.sha256(data).hexdigest()
    # A retried PutFile must never create a second version, even after a later external edit.
    if version_record(db, item, expected).sha256 == digest:
        return item, expected
    if item.version != expected:
        stem, extension = original.filename.rsplit(".", 1)
        item = WorkspaceFile(
            organization_id=original.organization_id,
            owner_id=original.owner_id,
            conversation_id=original.conversation_id,
            filename=stem[:145] + " (copie)." + extension,
            media_type=original.media_type,
        )
        db.add(item)
        db.flush()
        add_version(db, file_store(settings), item, data)
        shared = publication(db, original.id)
        if shared:
            db.add(
                ProjectFile(
                    organization_id=original.organization_id,
                    owner_id=original.owner_id,
                    project_id=shared.project_id,
                    file_id=item.id,
                    source_file_id=original.id,
                    source_version=session.base_version,
                )
            )
        session.conflict_file_id, session.conflict_version = item.id, item.version
    else:
        add_version(db, file_store(settings), item, data, expected)
        if session.conflict_file_id:
            session.conflict_version = item.version
        else:
            session.saved_version = item.version
    return item, item.version
