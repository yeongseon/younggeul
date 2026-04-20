"""LiteLLM adapter that validates structured JSON responses."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from importlib import import_module
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from ..metrics import (
    llm_cost_usd_total,
    llm_request_duration_seconds,
    llm_requests_total,
    llm_tokens_total,
    metric_attrs,
)
from .ports import LLMMessage

T = TypeVar("T", bound=BaseModel)

_KNOWN_PROVIDERS: frozenset[str] = frozenset(
    {
        "anthropic",
        "azure",
        "bedrock",
        "deepseek",
        "github",
        "openrouter",
        "replicate",
        "sagemaker",
        "vllm",
        "vertex_ai",
    }
)

_GITHUB_MODELS_PREFIX = "github/"
_GITHUB_MODELS_API_BASE = "https://models.github.ai/inference"


def _normalize_provider(model: str) -> str:
    """Extract the provider name from a LiteLLM model string.

    Args:
        model: LiteLLM model identifier (e.g. ``vllm/meta-llama/...``).

    Returns:
        Lower-cased provider name; ``"openai"`` for bare model names.
    """
    if not model:
        return "unknown"

    if "/" not in model:
        return "openai"

    prefix = model.split("/", 1)[0].lower()
    if prefix in _KNOWN_PROVIDERS:
        return prefix

    return "openai"


class _SpanLike(Protocol):
    def set_attribute(self, key: str, value: object) -> None: ...
    def set_status(self, status: object) -> None: ...
    def record_exception(self, exception: BaseException) -> None: ...


class _NoOpSpan:
    def set_attribute(self, _key: str, _value: object) -> None:
        pass

    def set_status(self, _status: object) -> None:
        pass

    def record_exception(self, _exception: BaseException) -> None:
        pass


@contextmanager
def _noop_span_ctx(**_kwargs: object) -> Iterator[_NoOpSpan]:
    yield _NoOpSpan()


def _make_span_ctx(name: str, attributes: dict[str, Any]) -> Any:
    try:
        from ..tracing import get_tracer

        return get_tracer().start_as_current_span(name, attributes=attributes)
    except Exception:
        return _noop_span_ctx()


def _set_error_status(span: _SpanLike, exc: Exception) -> None:
    try:
        from opentelemetry.trace import Status, StatusCode

        span.set_status(Status(StatusCode.ERROR, str(exc)))
        span.record_exception(exc)
    except Exception:
        pass


def _is_github_models_model(model: str) -> bool:
    return model.lower().startswith(_GITHUB_MODELS_PREFIX)


def _bridge_github_models_token() -> str | None:
    token = os.getenv("GH_MODELS_TOKEN") or os.getenv("GITHUB_TOKEN")
    if token and not os.getenv("GITHUB_TOKEN"):
        os.environ["GITHUB_TOKEN"] = token
    return token


def _resolve_completion_kwargs(model: str, default_kwargs: dict[str, Any]) -> dict[str, Any]:
    completion_kwargs = dict(default_kwargs)
    completion_kwargs["model"] = model

    if not _is_github_models_model(model):
        return completion_kwargs

    token = _bridge_github_models_token()
    if token is None:
        msg = "GitHub Models requires GH_MODELS_TOKEN or GITHUB_TOKEN"
        raise StructuredLLMTransportError(msg)

    completion_kwargs.update(
        {
            "model": model[len(_GITHUB_MODELS_PREFIX) :],
            "custom_llm_provider": "openai",
            "api_base": _GITHUB_MODELS_API_BASE,
            "api_key": token,
        }
    )
    return completion_kwargs


class StructuredLLMTransportError(RuntimeError):
    """Raised when transport-level LLM invocation fails."""

    pass


class StructuredLLMResponseError(ValueError):
    """Raised when LLM output is empty, invalid, or schema-incompatible."""

    pass


class LiteLLMStructuredLLM:
    """Structured LLM transport backed by the LiteLLM completion API."""

    def __init__(self, model: str, **default_kwargs: Any) -> None:
        self.model = model
        self._default_kwargs = default_kwargs

    def generate_structured(
        self,
        *,
        messages: Sequence[LLMMessage],
        response_model: type[T],
        temperature: float = 0.0,
    ) -> T:
        """Generate and validate a structured response from LiteLLM.

        Args:
            messages: Ordered chat messages sent to the model.
            response_model: Pydantic model used as the response schema.
            temperature: Sampling temperature for generation.

        Returns:
            Parsed and validated response model instance.

        Raises:
            StructuredLLMTransportError: When the model call fails.
            StructuredLLMResponseError: When output content is invalid.
        """
        litellm = import_module("litellm")

        schema = response_model.model_json_schema()
        response_format = {
            "type": "json_schema",
            "json_schema": {"name": response_model.__name__, "schema": schema},
        }

        span_attrs = {
            "llm.request.model": self.model,
            "llm.provider": _normalize_provider(self.model),
        }
        provider = _normalize_provider(self.model)
        request_metric_attrs = metric_attrs(provider=provider, model=self.model)
        start = time.monotonic()
        completion_kwargs = _resolve_completion_kwargs(self.model, self._default_kwargs)

        with _make_span_ctx("llm.completion", attributes=span_attrs) as span:
            try:
                response = litellm.completion(
                    messages=list(messages),
                    temperature=temperature,
                    response_format=response_format,
                    **completion_kwargs,
                )
            except Exception as exc:
                elapsed_ms = (time.monotonic() - start) * 1000
                llm_requests_total().add(
                    1,
                    attributes=metric_attrs(provider=provider, model=self.model, status="error"),
                )
                llm_request_duration_seconds().record(elapsed_ms / 1000, attributes=request_metric_attrs)
                span.set_attribute("llm.status", "error")
                span.set_attribute("llm.error.type", type(exc).__name__)
                span.set_attribute("llm.latency_ms", elapsed_ms)
                _set_error_status(span, exc)
                raise StructuredLLMTransportError(f"LLM call failed: {exc}") from exc

            elapsed_ms = (time.monotonic() - start) * 1000
            actual_model = getattr(response, "model", None)
            if isinstance(actual_model, str) and actual_model != self.model:
                span.set_attribute("llm.response.model", actual_model)

            usage = getattr(response, "usage", None)
            prompt_tokens: int | float | None = None
            completion_tokens: int | float | None = None
            if usage is not None:
                prompt_tokens = (
                    usage.get("prompt_tokens") if isinstance(usage, dict) else getattr(usage, "prompt_tokens", None)
                )
                completion_tokens = (
                    usage.get("completion_tokens")
                    if isinstance(usage, dict)
                    else getattr(usage, "completion_tokens", None)
                )
                total_tokens = (
                    usage.get("total_tokens") if isinstance(usage, dict) else getattr(usage, "total_tokens", None)
                )

                if prompt_tokens is not None:
                    span.set_attribute("llm.prompt_tokens", prompt_tokens)
                if completion_tokens is not None:
                    span.set_attribute("llm.completion_tokens", completion_tokens)
                if total_tokens is not None:
                    span.set_attribute("llm.total_tokens", total_tokens)

            hidden_params = getattr(response, "_hidden_params", None)
            cost_usd: float | None = None
            if isinstance(hidden_params, dict):
                raw_cost_usd = hidden_params.get("response_cost")
                if isinstance(raw_cost_usd, int | float):
                    cost_usd = float(raw_cost_usd)
                if cost_usd is not None:
                    span.set_attribute("llm.cost_usd", cost_usd)

            choices = getattr(response, "choices", None)
            if choices:
                finish_reason = getattr(choices[0], "finish_reason", None)
                if finish_reason is not None:
                    span.set_attribute("llm.finish_reason", finish_reason)

            span.set_attribute("llm.status", "success")
            span.set_attribute("llm.latency_ms", elapsed_ms)

            llm_requests_total().add(
                1,
                attributes=metric_attrs(provider=provider, model=self.model, status="success"),
            )
            llm_request_duration_seconds().record(elapsed_ms / 1000, attributes=request_metric_attrs)

            if isinstance(prompt_tokens, int | float):
                llm_tokens_total().add(
                    prompt_tokens,
                    attributes=metric_attrs(provider=provider, model=self.model, token_type="prompt"),
                )
            if isinstance(completion_tokens, int | float):
                llm_tokens_total().add(
                    completion_tokens,
                    attributes=metric_attrs(provider=provider, model=self.model, token_type="completion"),
                )
            if cost_usd is not None:
                llm_cost_usd_total().add(cost_usd, attributes=request_metric_attrs)

        raw_content = response.choices[0].message.content
        if raw_content is None:
            raise StructuredLLMResponseError("LLM returned empty content")

        try:
            data = json.loads(raw_content)
        except json.JSONDecodeError as exc:
            raise StructuredLLMResponseError(f"LLM returned invalid JSON: {raw_content[:200]}") from exc

        try:
            return response_model.model_validate(data)
        except ValidationError as exc:
            raise StructuredLLMResponseError(f"LLM output failed schema validation: {exc}") from exc
