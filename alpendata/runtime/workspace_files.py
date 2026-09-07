"""Access only attachments explicitly added to the current private conversation."""

import base64
import json
from pathlib import Path

from documents import read_workspace_file, save_download


def register_workspace_files(channel, registry):
    def access(arguments, **_):
        payload = dict(arguments)
        if payload.get("operation") == "save":
            content = read_workspace_file(payload.pop("path"), Path("/state/workspace"))
            payload["content_base64"] = base64.b64encode(content).decode("ascii")
        response = channel.exchange("tool", {"kind": "workspace_file", **payload})
        if response["status"] == 200 and arguments.get("operation") == "read":
            result = json.loads(save_download(response["body"]))
            result["passages"] = response["body"].get("passages", [])
            result["passages_partial"] = response["body"].get("passages_partial", False)
            return json.dumps(result, ensure_ascii=False)
        return json.dumps(
            {"status": response["status"], "result": response["body"]},
            ensure_ascii=False,
        )

    name = "alpendata_workspace_file"
    description = (
        "List, read, or save attachments in this conversation and explicitly published documents in its current project. Read returns a local file path. "
        "Read the file before claiming its contents. Cite filename/version and page, sheet or slide. "
        "Save requires the exact expected_version read previously and a relative workspace path; "
        "a version conflict must be shown to the user, never overwritten or silently retried."
    )
    registry.register(
        name=name,
        toolset="alpendata",
        handler=access,
        description=description,
        schema={
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "required": ["operation"],
                "additionalProperties": False,
                "properties": {
                    "operation": {"type": "string", "enum": ["list", "read", "save"]},
                    "file_id": {"type": "string"},
                    "version": {"type": "integer", "minimum": 1},
                    "expected_version": {"type": "integer", "minimum": 1},
                    "path": {"type": "string"},
                },
            },
        },
    )
