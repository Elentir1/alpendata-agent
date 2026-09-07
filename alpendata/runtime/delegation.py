"""Expose Hermes delegation as bounded, synchronous work inside the current execution."""

import json
import threading


def register_delegation(channel, registry, instructions, parent_context):
    used = 0
    execution_lock = threading.Lock()

    def execute(arguments, **kwargs):
        nonlocal used
        parent = parent_context.get("agent")
        tasks = arguments.get("tasks")
        if parent is None or getattr(parent, "_delegate_depth", 0) or used >= 2:
            return json.dumps({"status": 409, "error": "delegation_limit_reached"})
        if (
            not isinstance(tasks, list)
            or not 1 <= len(tasks) <= 2
            or any(
                not isinstance(item, dict)
                or set(item) - {"goal", "context"}
                or not isinstance(item.get("goal"), str)
                or not 1 <= len(item["goal"]) <= 2000
                or not isinstance(item.get("context", ""), str)
                or len(item.get("context", "")) > 8000
                for item in tasks
            )
        ):
            return json.dumps({"status": 400, "error": "delegation_tasks_invalid"})
        used += 1
        from tools.delegate_tool import delegate_task

        channel.background_models = True
        try:
            for index in range(len(tasks)):
                channel.exchange(
                    "activity",
                    {
                        "kind": "tool_started",
                        "label": f"delegated_task_{used}_{index + 1}",
                    },
                )
            result = json.loads(
                delegate_task(
                    tasks=[
                        {
                            "goal": task["goal"],
                            "context": instructions
                            + "\nTask context:\n"
                            + task.get("context", ""),
                        }
                        for task in tasks
                    ],
                    max_iterations=8,
                    background=False,
                    parent_agent=parent,
                )
            )
            return json.dumps(
                {
                    "results": [
                        {
                            key: item.get(key)
                            for key in ("task_index", "status", "summary")
                        }
                        for item in result.get("results", [])
                    ],
                    "error": result.get("error"),
                },
                ensure_ascii=False,
            )
        finally:
            channel.background_models = False
            for index in range(len(tasks)):
                channel.exchange(
                    "activity",
                    {
                        "kind": "tool_finished",
                        "label": f"delegated_task_{used}_{index + 1}",
                    },
                )

    def delegate(arguments, **kwargs):
        # A child must fail before taking this lock: the parent holds it while
        # waiting for children. Concurrent parent calls are serialized.
        parent = parent_context.get("agent")
        if parent is None or kwargs.get("session_id") != parent.session_id:
            return json.dumps({"status": 409, "error": "delegation_limit_reached"})
        with execution_lock:
            return execute(arguments, **kwargs)

    description = (
        "Ask up to two specialized Hermes workers to analyze independent parts of the current user task. "
        "They inherit this conversation's tools and permissions. Provide a clear bounded goal and relevant context. "
        "Wait for their results and verify the final synthesis. Do not delegate the same external action twice. "
        "All work remains inside this execution; no unrelated project or user is accessible."
    )
    registry.register(
        name="alpendata_delegate",
        toolset="alpendata",
        description=description,
        handler=delegate,
        schema={
            "name": "alpendata_delegate",
            "description": description,
            "parameters": {
                "type": "object",
                "required": ["tasks"],
                "additionalProperties": False,
                "properties": {
                    "tasks": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 2,
                        "items": {
                            "type": "object",
                            "required": ["goal"],
                            "additionalProperties": False,
                            "properties": {
                                "goal": {"type": "string"},
                                "context": {"type": "string"},
                            },
                        },
                    }
                },
            },
        },
    )
