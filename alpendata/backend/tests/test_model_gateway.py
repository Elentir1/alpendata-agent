import json

import pytest
from model_http import completion, model_http

from alpendata_api.model_gateway import BODY_LIMIT, ModelError, ModelGateway, ModelSettings


def test_routing_credentials_tools_and_usage_are_controlled_by_the_server(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://invalid-proxy.example:1")
    for provider, endpoint in (
        ("mistral", "https://api.mistral.ai/v1/chat/completions"),
        ("openrouter", "https://openrouter.ai/api/v1/chat/completions"),
    ):
        with model_http(lambda body: (200, completion(body), {})) as (session, received, destinations):
            settings = ModelSettings(
                provider,
                "operator-model",
                "synthetic-server-key",
                max_output_tokens=2048,
                allowed_providers=("Selected Provider",) if provider == "openrouter" else (),
            )
            gateway = ModelGateway(settings, session=session)
            payload = {
                "model": "unapproved-model",
                "base_url": "https://unapproved.example",
                "messages": [{"role": "user", "content": "Prepare my briefing."}],
                "tools": [{"type": "function", "function": {"name": "alpendata_mail", "parameters": {}}}],
                "provider": {"data_collection": "allow", "only": ["Unapproved"]},
                "plugins": [{"id": "web"}],
                "models": ["fallback-model"],
                "user": "private-owner-id",
                "stream": True,
                "n": 500,
                "max_tokens": 1000000,
                "usage": {"total_tokens": 0},
                "headers": {"Authorization": "Bearer worker-key"},
            }
            result = gateway.complete(payload)
            assert result.reply()["body"]["choices"][0]["message"]["content"] == "Synthetic answer"
            assert result.usage.total_tokens == 120 and result.usage.prompt_tokens == 100
            assert destinations == [endpoint]
            sent = received[0]
            assert sent["headers"]["Authorization"] == "Bearer synthetic-server-key"
            assert sent["body"]["messages"] == payload["messages"]
            assert sent["body"]["tools"] == payload["tools"]
            assert sent["body"]["model"] == settings.model
            assert sent["body"]["max_tokens"] == settings.max_output_tokens
            assert sent["body"]["stream"] is False and sent["body"]["n"] == 1
            assert not {"plugins", "models", "headers", "user", "usage", "base_url"} & sent["body"].keys()
            if provider == "openrouter":
                assert sent["body"]["provider"] == {
                    "data_collection": "deny",
                    "allow_fallbacks": False,
                    "require_parameters": True,
                    "only": ["Selected Provider"],
                }
            else:
                assert "provider" not in sent["body"]
            assert "synthetic-server-key" not in repr(settings)
            gateway.complete({**payload, "max_tokens": 64, "max_completion_tokens": 32})
            assert received[-1]["body"]["max_tokens"] == 32


def test_invalid_content_cannot_enable_provider_tools_or_external_fetches():
    with model_http(lambda body: (200, completion(body), {})) as (session, received, _):
        gateway = ModelGateway(ModelSettings("mistral", "operator-model", "synthetic-key"), session=session)
        text = {"messages": [{"role": "user", "content": "Confidential client content"}]}
        invalid = [
            {
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": "https://unapproved.example/private",
                                },
                            }
                        ],
                    }
                ]
            },
            {**text, "tools": [{"type": "web_search"}]},
            {**text, "tools": [{"type": "code_interpreter"}]},
            {**text, "max_tokens": True},
            {**text, "temperature": float("nan")},
        ]
        for payload in invalid:
            with pytest.raises(ModelError, match="^model_request_invalid$") as error:
                gateway.complete(payload)
            assert error.value.status == 400
        with pytest.raises(ModelError, match="model_request_too_large"):
            gateway.complete({"messages": [{"role": "user", "content": "x" * BODY_LIMIT}]})
        assert not received


def test_http_errors_are_bounded_sanitized_and_never_followed_or_retried():
    response = [200, {}, {}]
    with model_http(lambda _: tuple(response)) as (session, received, destinations):
        gateway = ModelGateway(
            ModelSettings("openrouter", "operator-model", "synthetic-key"), session=session
        )
        payload = {"messages": [{"role": "user", "content": "Private prompt"}]}
        cases = [
            (
                302,
                b"private upstream diagnostic",
                {"Location": "https://unapproved.example"},
                502,
                "model_unavailable",
            ),
            (401, b"private upstream diagnostic", {}, 503, "model_configuration_required"),
            (429, b"private upstream diagnostic", {"Retry-After": "9000"}, 429, "model_rate_limited"),
            (500, b"private upstream diagnostic", {}, 502, "model_unavailable"),
            (200, b"not-json: private upstream diagnostic", {}, 502, "model_unavailable"),
            (200, {"error": {"message": "private upstream diagnostic"}}, {}, 502, "model_response_invalid"),
            (200, {"choices": []}, {}, 502, "model_response_invalid"),
            (200, b" " * (BODY_LIMIT + 1), {}, 502, "model_response_too_large"),
        ]
        for status, body, headers, expected_status, code in cases:
            response[:] = status, body, headers
            before = len(received)
            with pytest.raises(ModelError, match="^" + code + "$") as error:
                gateway.complete(payload)
            assert error.value.status == expected_status
            assert len(received) == before + 1
            if status == 429:
                assert error.value.retry_after == 3600
        assert len(destinations) == len(cases)


def test_missing_or_malformed_usage_is_unknown_and_never_fabricated():
    payload = {"messages": [{"role": "user", "content": "Hello"}]}
    data = completion({"model": "operator-model"})
    with model_http(lambda _: (200, data, {})) as (session, _, _):
        gateway = ModelGateway(ModelSettings("mistral", "operator-model", "synthetic-key"), session=session)
        for usage in (
            None,
            {},
            {"prompt_tokens": True, "completion_tokens": 1, "total_tokens": 2},
            {"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 0},
        ):
            data["usage"] = usage
            result = gateway.complete(payload)
            assert result.usage is None
            assert "Synthetic answer" in json.dumps(result.reply())


def test_openrouter_tool_continuation_preserves_reasoning_and_structured_output():
    reasoning = [
        {
            "type": "reasoning.encrypted",
            "data": "synthetic-opaque-block",
            "id": None,
            "format": "anthropic-claude-v1",
            "index": 0,
        }
    ]
    assistant = {
        "role": "assistant",
        "reasoning_details": reasoning,
        "tool_calls": [
            {"type": "function", "id": "call_1", "function": {"name": "alpendata_mail", "arguments": "{}"}}
        ],
    }
    messages = [
        {"role": "user", "content": "Prepare a briefing"},
        assistant,
        {"role": "tool", "tool_call_id": "call_1", "content": "Synthetic client message"},
    ]
    choice = {"type": "function", "function": {"name": "alpendata_mail"}}
    with model_http(lambda body: (200, completion(body), {})) as (session, received, _):
        gateway = ModelGateway(
            ModelSettings("openrouter", "operator-model", "synthetic-key"), session=session
        )
        gateway.complete(
            {"messages": messages, "tool_choice": choice, "response_format": {"type": "json_object"}}
        )
        sent = received[0]["body"]
        assert sent["messages"] == messages
        assert sent["tool_choice"] == choice
        assert sent["response_format"] == {"type": "json_object"}
