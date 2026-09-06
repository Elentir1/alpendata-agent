"""Preparation only. Sending is exclusively an authenticated application action."""

import json


def register_emails(channel, registry):
    name = "alpendata_prepare_email"
    description = (
        "Prepare a private editable email in chat for the user to review and send. "
        "Does not send or create an Outlook draft. Never invent recipient addresses. "
        "Attach only IDs from published documents; at most 2 MiB total."
    )

    def prepare(arguments, **_):
        response = channel.exchange("tool", {**arguments, "kind": "mail_draft"})
        return json.dumps(
            {"status": response["status"], "result": response["body"]},
            ensure_ascii=False,
        )

    registry.register(
        name=name,
        toolset="alpendata",
        description=description,
        handler=prepare,
        schema={
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "required": ["to", "subject", "body"],
                "properties": {
                    **{
                        key: {
                            "type": "array",
                            "items": {"type": "string"},
                            "maxItems": 20,
                            **({"minItems": 1} if key == "to" else {}),
                        }
                        for key in ("to", "cc", "bcc")
                    },
                    "subject": {"type": "string", "minLength": 1, "maxLength": 998},
                    "body": {"type": "string", "minLength": 1, "maxLength": 32000},
                    "attachment_ids": {
                        "type": "array",
                        "maxItems": 5,
                        "items": {"type": "string", "format": "uuid"},
                    },
                },
            },
        },
    )
