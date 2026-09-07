import json


def register_calendar(channel, registry):
    def handle(arguments, **_):
        result = channel.exchange("tool", {"kind": "calendar_action", **arguments})
        return json.dumps(
            {"status": result["status"], "result": result["body"]}, ensure_ascii=False
        )

    description = (
        "Prepare a calendar appointment for review, or execute a prepared proposal only when "
        "the user's autonomy and company permissions authorize it. Start/end must include explicit timezone offsets. "
        "Inviting attendees can notify them. Include all desired attendees, location and description. "
        "For updates use event_id and calendar_id from the connected calendar. Recurring event edits need manual handling. "
        "Never replay unknown or dispatching results. A prepared proposal has not been saved to the calendar."
    )
    registry.register(
        name="alpendata_calendar_action",
        toolset="alpendata",
        description=description,
        handler=handle,
        schema={
            "name": "alpendata_calendar_action",
            "description": description,
            "parameters": {
                "type": "object",
                "required": ["operation"],
                "additionalProperties": False,
                "properties": {
                    "operation": {"type": "string", "enum": ["prepare", "execute"]},
                    "action_id": {"type": "string"},
                    "version": {"type": "integer"},
                    "event": {
                        "type": "object",
                        "required": ["subject", "start", "end"],
                        "additionalProperties": False,
                        "properties": {
                            **{
                                key: {"type": "string"}
                                for key in (
                                    "subject",
                                    "description",
                                    "start",
                                    "end",
                                    "location",
                                    "event_id",
                                    "calendar_id",
                                )
                            },
                            "attendees": {
                                "type": "array",
                                "maxItems": 20,
                                "items": {"type": "string"},
                            },
                        },
                    },
                },
            },
        },
    )
