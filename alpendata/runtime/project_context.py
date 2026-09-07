"""Project resources are fetched by the owner-bound broker, never a filesystem mount."""

import json


def register_project_context(channel, registry):
    name = "alpendata_project_context"

    def read(arguments, **_):
        response = channel.exchange("tool", {"kind": "project_context", **arguments})
        return json.dumps(
            {"status": response["status"], "result": response["body"]},
            ensure_ascii=False,
        )

    registry.register(
        name=name,
        toolset="alpendata",
        handler=read,
        description="List published resources in the current project, or read one by ID. No other project is accessible.",
        schema={
            "name": name,
            "description": "Read explicitly published current-project knowledge.",
            "parameters": {
                "type": "object",
                "properties": {"entry_id": {"type": "string"}},
                "additionalProperties": False,
            },
        },
    )
