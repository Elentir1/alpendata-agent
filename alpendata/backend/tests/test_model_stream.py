import json

import pytest
from model_http import completion, model_http

from alpendata_api.model_gateway import ModelError, ModelGateway, ModelSettings


def event(delta=None, finish=None, usage=None):
    value = {"choices": [{"index": 0, "delta": delta or {}, "finish_reason": finish}]}
    if usage:
        value["usage"] = usage
    return b"data: " + json.dumps(value).encode() + b"\n\n"


def test_streamed_text_and_fragmented_tools_preserve_usage_without_exposing_reasoning():
    body = event({"reasoning_content": "private internal reasoning"})
    body += event({"content": "Bonjour "}) + event({"content": "David"})
    body += event(
        {"tool_calls": [{"index": 0, "id": "call_1", "function": {"name": "mail", "arguments": '{"query":'}}]}
    )
    body += event({"tool_calls": [{"index": 0, "function": {"arguments": '"client"}'}}]}, "tool_calls")
    body += (
        event(usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}) + b"data: [DONE]\n\n"
    )
    with model_http(lambda _: (200, body, {"Content-Type": "text/event-stream"})) as (session, received, _):
        gateway = ModelGateway(ModelSettings("mistral", "operator-model", "synthetic-key"), session=session)
        visible = []
        result = gateway.complete_stream(
            {"messages": [{"role": "user", "content": "Bonjour"}]}, visible.append
        )
        assert visible == ["Bonjour ", "Bonjour David"]
        message = result.reply()["body"]["choices"][0]["message"]
        assert message["tool_calls"][0]["function"]["arguments"] == '{"query":"client"}'
        assert message["reasoning_content"] == "private internal reasoning"
        assert result.usage.total_tokens == 15
        assert received[0]["body"]["stream"] is True
        assert received[0]["headers"]["Authorization"] == "Bearer synthetic-key"


def test_stream_interruption_is_not_retried_or_reported_as_a_completed_answer():
    with model_http(
        lambda _: (200, event({"content": "Partial"}), {"Content-Type": "text/event-stream"})
    ) as (session, received, _):
        gateway = ModelGateway(ModelSettings("mistral", "operator-model", "synthetic-key"), session=session)
        visible = []
        with pytest.raises(ModelError, match="model_stream_interrupted"):
            gateway.complete_stream({"messages": [{"role": "user", "content": "Hello"}]}, visible.append)
        assert visible == ["Partial"] and len(received) == 1


def test_provider_json_fallback_uses_the_same_request():
    with model_http(lambda body: (200, completion(body), {})) as (session, received, _):
        gateway = ModelGateway(ModelSettings("mistral", "operator-model", "synthetic-key"), session=session)
        result = gateway.complete_stream({"messages": [{"role": "user", "content": "Hello"}]}, lambda _: None)
        assert result.usage.total_tokens == 120 and len(received) == 1
