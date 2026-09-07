import json


def register_vision(channel, registry):
    description = (
        "Read an explicitly attached or current-project image with the configured Mistral vision specialist. "
        "Specify the exact file_id and version returned by alpendata_workspace_file. "
        "The result identifies the specialist model; cite it and the image version when describing findings."
    )
    registry.register(
        name="alpendata_read_image",
        toolset="alpendata",
        description=description,
        handler=lambda arguments, **_: json.dumps(
            channel.exchange("tool", {"kind": "vision", **arguments}),
            ensure_ascii=False,
        ),
        schema={
            "name": "alpendata_read_image",
            "description": description,
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "required": ["file_id", "version", "question"],
                "properties": {
                    "file_id": {"type": "string"},
                    "version": {"type": "integer", "minimum": 1},
                    "question": {"type": "string"},
                },
            },
        },
    )
