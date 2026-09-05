"""Server-owned model routing for the isolated Hermes runtime.

The worker supplies conversation content, never credentials, destinations or a
provider's executable tools. Usage is read from the HTTP response, not the worker.
"""

import json
import re
import time
from contextlib import nullcontext
from dataclasses import dataclass, field
from typing import Literal

import requests
from pydantic import BaseModel, ConfigDict, Field, ValidationError

BODY_LIMIT = 6 * 1024 * 1024
ENDPOINTS = {
    "mistral": "https://api.mistral.ai/v1/chat/completions",
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
}


class ModelError(Exception):
    def __init__(self, status: int, code: str, retry_after: int = 0):
        self.status, self.code, self.retry_after = status, code, retry_after
        super().__init__(code)


@dataclass(frozen=True)
class ModelSettings:
    provider: str
    model: str
    api_key: str = field(repr=False)
    max_output_tokens: int = 8192
    timeout_seconds: int = 60
    allowed_providers: tuple[str, ...] = ()

    def __post_init__(self):
        if self.provider not in ENDPOINTS:
            raise ValueError("Choose mistral or openrouter")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}", self.model):
            raise ValueError("Invalid model identifier")
        if not self.api_key or any(ord(char) < 33 or ord(char) > 126 for char in self.api_key):
            raise ValueError("A provider credential is required")
        if not 1 <= self.max_output_tokens <= 65536 or not 5 <= self.timeout_seconds <= 120:
            raise ValueError("Invalid model execution limits")
        if self.allowed_providers and self.provider != "openrouter":
            raise ValueError("Provider routing applies only to OpenRouter")
        if any(not name.strip() or len(name) > 100 for name in self.allowed_providers):
            raise ValueError("Invalid OpenRouter provider selection")


class FunctionCall(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    name: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    arguments: str


class ToolCall(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    id: str = Field(min_length=1, max_length=256)
    type: Literal["function"]
    function: FunctionCall


class Message(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    tool_calls: list[ToolCall] | None = Field(default=None, max_length=128)
    tool_call_id: str | None = Field(default=None, min_length=1, max_length=256)
    name: str | None = Field(default=None, min_length=1, max_length=128)
    reasoning: str | None = None
    reasoning_content: str | None = None
    reasoning_details: list[dict] | None = None


class FunctionDefinition(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    name: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    description: str | None = None
    parameters: dict
    strict: bool | None = None


class ToolDefinition(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    type: Literal["function"]
    function: FunctionDefinition


class NamedFunction(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    name: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


class ToolChoice(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    type: Literal["function"]
    function: NamedFunction


class ResponseFormat(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    type: Literal["text", "json_object", "json_schema"]
    json_schema: dict | None = None


class ModelRequest(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True, allow_inf_nan=False)
    messages: list[Message] = Field(min_length=1, max_length=4096)
    tools: list[ToolDefinition] | None = Field(default=None, max_length=128)
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, gt=0, le=1)
    max_tokens: int | None = Field(default=None, ge=1)
    max_completion_tokens: int | None = Field(default=None, ge=1)
    parallel_tool_calls: bool | None = None
    tool_choice: Literal["auto", "none", "required", "any"] | ToolChoice | None = None
    response_format: ResponseFormat | None = None


@dataclass(frozen=True)
class ModelUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

    @classmethod
    def from_response(cls, value):
        if not isinstance(value, dict):
            return None
        names = ("prompt_tokens", "completion_tokens", "total_tokens")
        if any(type(value.get(name)) is not int or not 0 <= value[name] <= 2**63 - 1 for name in names):
            return None
        if value["total_tokens"] < value["prompt_tokens"] + value["completion_tokens"]:
            return None
        return cls(**{name: value[name] for name in names})


@dataclass(frozen=True)
class ModelCompletion:
    body: dict = field(repr=False)
    usage: ModelUsage | None

    def reply(self):
        return {"status": 200, "body": self.body}


class ModelGateway:
    def __init__(self, settings: ModelSettings, *, session=None):
        self.settings, self.session = settings, session

    def request_body(self, payload):
        try:
            request = ModelRequest.model_validate(payload)
            body = request.model_dump(exclude_none=True, exclude={"max_completion_tokens"})
            if self.settings.provider == "mistral":
                # Mistral's thinking chunks have a different schema; do not send
                # or silently discard a reasoning context in an incompatible format.
                for message in body["messages"]:
                    if {"reasoning", "reasoning_content", "reasoning_details"} & message.keys():
                        raise ModelError(400, "model_content_unsupported")
            # Smaller auxiliary requests (e.g. titles) retain their own limit.
            limits = [self.settings.max_output_tokens, request.max_tokens, request.max_completion_tokens]
            body.update(
                model=self.settings.model,
                stream=False,
                n=1,
                max_tokens=min(limit for limit in limits if limit is not None),
            )
            if self.settings.provider == "openrouter":
                body["provider"] = {
                    "data_collection": "deny",
                    "allow_fallbacks": False,
                    "require_parameters": True,
                }
                if self.settings.allowed_providers:
                    body["provider"]["only"] = list(self.settings.allowed_providers)
            encoded = json.dumps(body, ensure_ascii=True, allow_nan=False).encode()
            if len(encoded) > BODY_LIMIT:
                raise ModelError(413, "model_request_too_large")
            return encoded
        except (ValidationError, ValueError, TypeError, RecursionError):
            # Validation errors can include the original confidential input.
            raise ModelError(400, "model_request_invalid") from None

    def complete(self, payload):
        encoded = self.request_body(payload)
        started = time.monotonic()
        try:
            with nullcontext(self.session) if self.session is not None else requests.Session() as transport:
                transport.trust_env = False
                with transport.post(
                    ENDPOINTS[self.settings.provider],
                    data=encoded,
                    headers={
                        "Authorization": "Bearer " + self.settings.api_key,
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    timeout=(5, self.settings.timeout_seconds),
                    allow_redirects=False,
                    stream=True,
                ) as response:
                    self.check_status(response)
                    content = bytearray()
                    for chunk in response.iter_content(65536):
                        if time.monotonic() - started > self.settings.timeout_seconds:
                            raise ModelError(504, "model_timed_out")
                        content.extend(chunk)
                        if len(content) > BODY_LIMIT:
                            raise ModelError(502, "model_response_too_large")
                    data = json.loads(content)
                    if not isinstance(data, dict) or data.get("error"):
                        raise ModelError(502, "model_response_invalid")
                    choices = data.get("choices")
                    if (
                        not isinstance(choices, list)
                        or len(choices) != 1
                        or not isinstance(choices[0], dict)
                        or not isinstance(choices[0].get("message"), dict)
                        or choices[0]["message"].get("role") != "assistant"
                    ):
                        raise ModelError(502, "model_response_invalid")
                    body = {
                        key: data[key]
                        for key in ("id", "object", "created", "model", "choices", "usage")
                        if key in data
                    }
                    return ModelCompletion(body, ModelUsage.from_response(data.get("usage")))
        except requests.Timeout:
            raise ModelError(504, "model_timed_out") from None
        except (requests.RequestException, ValueError, RecursionError):
            raise ModelError(502, "model_unavailable") from None

    @staticmethod
    def check_status(response):
        if response.status_code == 200:
            return
        if response.status_code in {401, 402, 403}:
            raise ModelError(503, "model_configuration_required")
        if response.status_code == 429:
            delay = response.headers.get("Retry-After", "60")
            retry_after = min(3600, max(1, int(delay))) if delay.isascii() and delay.isdigit() else 60
            raise ModelError(429, "model_rate_limited", retry_after)
        raise ModelError(502, "model_unavailable")
