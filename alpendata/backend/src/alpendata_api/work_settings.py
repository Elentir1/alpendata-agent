from typing import Literal

from pydantic import Field

from .schemas import Input


class WorkSettings(Input):
    depth: Literal["quick", "balanced", "deep"] = "balanced"
    sources: list[Literal["mail", "calendar", "files", "documents", "project", "web"]] = Field(
        default_factory=lambda: ["mail", "calendar", "files", "documents", "project", "web"], max_length=6
    )
    autonomy: Literal["prepare", "confirm", "authorized"] = "confirm"


def source_allowed(conversation, source):
    return conversation.work_settings is None or source in conversation.work_settings.get("sources", [])
