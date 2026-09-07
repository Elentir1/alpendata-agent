"""Read provider SSE and reconstruct the canonical response for Hermes' JSON broker."""

import json
import time
from contextlib import nullcontext

import requests

from .model_gateway import BODY_LIMIT, ENDPOINTS, ModelCompletion, ModelError, ModelUsage


def complete_stream(gateway, payload, on_text):
    body = json.loads(gateway.request_body(payload))
    body.update(stream=True, stream_options={"include_usage": True})
    started = time.monotonic()
    message, calls, metadata = {"role": "assistant", "content": ""}, {}, {}
    finish, usage, done = None, None, False
    try:
        with nullcontext(gateway.session) if gateway.session is not None else requests.Session() as transport:
            transport.trust_env = False
            with transport.post(
                ENDPOINTS[gateway.settings.provider],
                data=json.dumps(body).encode(),
                headers={
                    "Authorization": "Bearer " + gateway.settings.api_key,
                    "Content-Type": "application/json",
                    "Accept": "text/event-stream",
                },
                timeout=(5, gateway.settings.timeout_seconds),
                allow_redirects=False,
                stream=True,
            ) as response:
                gateway.check_status(response)
                if "text/event-stream" not in response.headers.get("Content-Type", ""):
                    content = bytearray()
                    for chunk in response.iter_content(65536):
                        content.extend(chunk)
                        if len(content) > BODY_LIMIT:
                            raise ModelError(502, "model_response_too_large")
                    value = json.loads(content)
                    if (
                        not isinstance(value, dict)
                        or len(value.get("choices", [])) != 1
                        or value["choices"][0].get("message", {}).get("role") != "assistant"
                    ):
                        raise ModelError(502, "model_response_invalid")
                    return ModelCompletion(value, ModelUsage.from_response(value.get("usage")))
                size = 0
                for line in response.iter_lines(chunk_size=256):
                    size += len(line)
                    if size > BODY_LIMIT:
                        raise ModelError(502, "model_response_too_large")
                    if time.monotonic() - started > gateway.settings.timeout_seconds:
                        raise ModelError(504, "model_timed_out")
                    if not line.startswith(b"data:"):
                        continue
                    data = line[5:].strip()
                    if data == b"[DONE]":
                        done = True
                        break
                    event = json.loads(data)
                    if not isinstance(event, dict) or event.get("error"):
                        raise ModelError(502, "model_response_invalid")
                    metadata.update({key: event[key] for key in ("id", "model", "created") if key in event})
                    if event.get("usage"):
                        usage = event["usage"]
                    for choice in event.get("choices", []):
                        if choice.get("index", 0) != 0:
                            raise ModelError(502, "model_response_invalid")
                        delta = choice.get("delta", {})
                        content = delta.get("content")
                        if content is not None:
                            if not isinstance(content, str):
                                raise ModelError(502, "model_content_unsupported")
                            message["content"] += content
                            on_text(message["content"])
                        for key in ("reasoning", "reasoning_content"):
                            if isinstance(delta.get(key), str):
                                message[key] = message.get(key, "") + delta[key]
                        for tool in delta.get("tool_calls", []):
                            index = tool.get("index")
                            if type(index) is not int or not 0 <= index < 128:
                                raise ModelError(502, "model_response_invalid")
                            call = calls.setdefault(
                                index,
                                {"id": "", "type": "function", "function": {"name": "", "arguments": ""}},
                            )
                            if tool.get("id"):
                                call["id"] = tool["id"]
                            for key in ("name", "arguments"):
                                value = tool.get("function", {}).get(key)
                                if value is not None:
                                    if not isinstance(value, str):
                                        raise ModelError(502, "model_response_invalid")
                                    call["function"][key] += value
                        if choice.get("finish_reason"):
                            finish = choice["finish_reason"]
                if not done or not finish:
                    raise ModelError(502, "model_stream_interrupted")
                if calls:
                    message["tool_calls"] = [calls[key] for key in sorted(calls)]
                result = {
                    **metadata,
                    "object": "chat.completion",
                    "choices": [{"index": 0, "message": message, "finish_reason": finish}],
                    "usage": usage,
                }
                return ModelCompletion(result, ModelUsage.from_response(usage))
    except requests.Timeout:
        raise ModelError(504, "model_timed_out") from None
    except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError):
        raise ModelError(502, "model_response_invalid") from None
