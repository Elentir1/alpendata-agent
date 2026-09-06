"""Owner-requested memory maintenance, without starting an agent or a model call."""

import hashlib
import os
import stat
from pathlib import Path

from tools.memory_tool_store import ENTRY_DELIMITER, MemoryStore
from tools.threat_patterns import first_threat_message

MAX_BYTES = 64 * 1024
TARGETS = {"memory": "MEMORY.md", "user": "USER.md"}


class MemoryError(Exception):
    pass


def checked_file(path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise MemoryError("memory_state_invalid")


def directory():
    home = Path(os.environ["HERMES_HOME"])
    location = home / "memories"
    for path in (home, location):
        if path.is_symlink():
            raise MemoryError("memory_state_invalid")
        path.mkdir(mode=0o700, exist_ok=True)
    for name in TARGETS.values():
        checked_file(location / name)
        checked_file(location / (name + ".lock"))
    return location


def read_target(location, target, store):
    path = location / TARGETS[target]
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        raw = b""
    else:
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise MemoryError("memory_state_invalid")
            raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise MemoryError("memory_too_large")
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise MemoryError("memory_unreadable") from None
    return {
        "version": hashlib.sha256(raw).hexdigest(),
        "entries": list(dict.fromkeys(MemoryStore._parse_entries(content))),
        "limit": store._char_limit(target),
    }


def manage(request):
    try:
        location, store = directory(), MemoryStore()
        if request.get("action") == "update":
            target = request.get("target")
            if target not in TARGETS:
                raise MemoryError("memory_request_invalid")
            current = read_target(location, target, store)
            if request.get("version") != current["version"]:
                raise MemoryError("memory_changed")
            entries = request.get("entries")
            if not isinstance(entries, list) or not all(
                isinstance(value, str) for value in entries
            ):
                raise MemoryError("memory_request_invalid")
            entries = [value.strip() for value in entries if value.strip()]
            if any(ENTRY_DELIMITER in value for value in entries):
                raise MemoryError("memory_request_invalid")
            if len(ENTRY_DELIMITER.join(entries)) > current["limit"]:
                raise MemoryError("memory_limit_exceeded")
            if any(first_threat_message(value, scope="strict") for value in entries):
                raise MemoryError("memory_content_rejected")
            entries = list(dict.fromkeys(entries))
            # This is a whole-list replacement explicitly reviewed by the owner,
            # against the raw file hash. Preserve Hermes' lock and atomic writer;
            # its model-facing drift guard is unnecessary for this reviewed view.
            result = store._mutate(
                target, lambda _old, _limit: (entries, "Updated"), skip_drift=True
            )
            if not result.get("success"):
                raise MemoryError("memory_update_failed")
        elif request.get("action") != "read":
            raise MemoryError("memory_request_invalid")
        return {"memory": {key: read_target(location, key, store) for key in TARGETS}}
    except MemoryError as error:
        return {"memory_error": str(error)}
    except OSError:
        return {"memory_error": "memory_unavailable"}
