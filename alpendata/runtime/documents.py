"""Publish workspace files through the private, authenticated host broker."""

import base64
import json
import os
import stat
import re
from pathlib import Path, PurePosixPath
from uuid import uuid4

MAX_BYTES = 5 * 1024 * 1024


def read_workspace_file(relative_path, workspace):
    """Open each component without following links, including concurrent swaps."""
    path = PurePosixPath(relative_path)
    if (
        not relative_path
        or path.is_absolute()
        or ".." in path.parts
        or "\\" in relative_path
    ):
        raise ValueError("document_path_invalid")
    descriptor = os.open(workspace, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parts[:-1]:
            child = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor
            )
            os.close(descriptor)
            descriptor = child
        file = os.open(
            path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor
        )
        with os.fdopen(file, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
                raise ValueError("document_too_large_or_invalid")
            content = stream.read(MAX_BYTES + 1)
        if not content or len(content) > MAX_BYTES:
            raise ValueError("document_too_large_or_invalid")
        return content
    finally:
        os.close(descriptor)


def register_download(channel, registry):
    def download(arguments, **_):
        response = channel.exchange(
            "tool",
            {
                "capability": "files",
                "operation": "download",
                "arguments": arguments,
            },
        )
        if response["status"] != 200:
            return json.dumps({
                "status": response["status"],
                "result": response["body"],
            })
        body = response["body"]
        content = base64.b64decode(body["content_base64"], validate=True)
        if len(content) > MAX_BYTES:
            return json.dumps({"status": 413, "error": "document_too_large"})
        source = body["files"][0]
        suffix = PurePosixPath(source["name"]).suffix.lower()
        if not re.fullmatch(r"\.[a-z0-9]{1,12}", suffix):
            suffix = ".bin"
        filename = source["name"]
        if (
            not filename
            or len(filename) > 180
            or filename.startswith(".")
            or any(
                character in '<>:"/\\|?*' or ord(character) < 32
                for character in filename
            )
        ):
            filename = "document" + suffix
        folder = uuid4().hex
        workspace = os.open(
            "/state/workspace", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        )
        try:
            try:
                os.mkdir("sources", mode=0o700, dir_fd=workspace)
            except FileExistsError:
                pass
            directory = os.open(
                "sources",
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=workspace,
            )
            try:
                os.mkdir(folder, mode=0o700, dir_fd=directory)
                destination = os.open(
                    folder,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=directory,
                )
                try:
                    descriptor = os.open(
                        filename,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                        0o600,
                        dir_fd=destination,
                    )
                    with os.fdopen(descriptor, "wb") as file:
                        file.write(content)
                finally:
                    os.close(destination)
            finally:
                os.close(directory)
        finally:
            os.close(workspace)
        return json.dumps(
            {"status": 200, "file": source, "path": f"sources/{folder}/{filename}"},
            ensure_ascii=False,
        )

    name = "alpendata_download_file"
    description = (
        "Download a file that the signed-in user's Microsoft account can read, using its drive_id and id "
        "from alpendata_files search. Returns a private local path for reading or editing with file/terminal tools. "
        "Maximum 5 MiB. Does not change SharePoint. Read the local file before claiming its contents were reviewed."
    )
    registry.register(
        name=name,
        toolset="alpendata",
        description=description,
        handler=download,
        schema={
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "required": ["drive_id", "item_id"],
                "additionalProperties": False,
                "properties": {
                    key: {"type": "string", "minLength": 1, "maxLength": 512}
                    for key in ("drive_id", "item_id")
                },
            },
        },
    )


def register_documents(channel, registry):
    def publish(arguments, **_):
        try:
            if set(arguments) != {"path"} or not isinstance(arguments["path"], str):
                raise ValueError("document_path_invalid")
            content = read_workspace_file(arguments["path"], Path("/state/workspace"))
            reply = channel.exchange(
                "tool",
                {
                    "kind": "document",
                    "filename": PurePosixPath(arguments["path"]).name,
                    "content_base64": base64.b64encode(content).decode("ascii"),
                },
            )
            return json.dumps(
                {"status": reply["status"], "result": reply["body"]}, ensure_ascii=False
            )
        except (OSError, ValueError):
            return json.dumps({"status": 400, "error": "document_file_unavailable"})

    name = "alpendata_publish_document"
    description = (
        "Make an existing PDF, DOCX, XLSX or PPTX available as a private chat download. "
        "First create and check the file using terminal/file tools. Pass its relative path within "
        "/state/workspace. Maximum 5 MiB per file. Does not upload to SharePoint or send a message. "
        "A successful result means the bytes are saved; it does not validate content or layout."
    )
    registry.register(
        name=name,
        toolset="alpendata",
        description=description,
        handler=publish,
        schema={
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "required": ["path"],
                "additionalProperties": False,
                "properties": {
                    "path": {"type": "string", "minLength": 1, "maxLength": 1024}
                },
            },
        },
    )
