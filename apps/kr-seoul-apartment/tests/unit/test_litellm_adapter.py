from __future__ import annotations

from importlib import import_module
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode, Tracer
from pydantic import BaseModel

litellm_adapter_module = import_module("younggeul_app_kr_seoul_apartment.simulation.llm.litellm_adapter")

LiteLLMStructuredLLM = litellm_adapter_module.LiteLLMStructuredLLM
StructuredLLMTransportError = litellm_adapter_module.StructuredLLMTransportError
StructuredLLMResponseError = litellm_adapter_module.StructuredLLMResponseError
_normalize_provider = litellm_adapter_module._normalize_provider
_NoOpSpan = litellm_adapter_module._NoOpSpan


class _StructuredResponse(BaseModel):
    message: str


def _choice(content: str, *, finish_reason: str = "stop") -> SimpleNamespace:
    return SimpleNamespace(message=SimpleNamespace(content=content), finish_reason=finish_reason)


def _make_test_tracer() -> tuple[Tracer, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer("unit-test"), exporter


def _span_attributes(span: object) -> dict[str, object]:
    attrs = getattr(span, "attributes")
    assert attrs is not None
    return dict(attrs)


# ---------------------------------------------------------------------------
# _normalize_provider tests
# ---------------------------------------------------------------------------


class TestNormalizeProvider:
    def test_bare_openai_model(self) -> None:
        assert _normalize_provider("gpt-4") == "openai"

    def test_bare_openai_model_with_version(self) -> None:
        assert _normalize_provider("gpt-4-turbo-2024-04-09") == "openai"

    def test_vllm_prefix(self) -> None:
        assert _normalize_provider("vllm/model") == "vllm"

    def test_vllm_nested_slashes(self) -> None:
        assert _normalize_provider("vllm/meta-llama/Meta-Llama-3.1-8B-Instruct") == "vllm"

    def test_anthropic_prefix(self) -> None:
        assert _normalize_provider("anthropic/claude-3") == "anthropic"

    def test_anthropic_full_model(self) -> None:
        assert _normalize_provider("anthropic/claude-3-5-sonnet-20241022") == "anthropic"

    def test_azure_prefix(self) -> None:
        assert _normalize_provider("azure/my-deployment") == "azure"

    def test_bedrock_prefix(self) -> None:
        assert _normalize_provider("bedrock/anthropic.claude-v2") == "bedrock"

    def test_deepseek_prefix(self) -> None:
        assert _normalize_provider("deepseek/deepseek-chat") == "deepseek"

    def test_openrouter_prefix(self) -> None:
        assert _normalize_provider("openrouter/meta-llama/llama-3-70b") == "openrouter"

    def test_replicate_prefix(self) -> None:
        assert _normalize_provider("replicate/meta/llama-2-70b") == "replicate"

    def test_sagemaker_prefix(self) -> None:
        assert _normalize_provider("sagemaker/my-endpoint") == "sagemaker"

    def test_vertex_ai_prefix(self) -> None:
        assert _normalize_provider("vertex_ai/gemini-pro") == "vertex_ai"

    def test_case_insensitive_prefix(self) -> None:
        assert _normalize_provider("Anthropic/claude-3") == "anthropic"
        assert _normalize_provider("VLLM/model") == "vllm"
        assert _normalize_provider("Azure/gpt-4") == "azure"

    def test_unknown_org_prefix_defaults_to_openai(self) -> None:
        assert _normalize_provider("meta-llama/Meta-Llama-3") == "openai"

    def test_unknown_org_huggingface_style(self) -> None:
        assert _normalize_provider("mistralai/Mistral-7B") == "openai"

    def test_empty_string(self) -> None:
        assert _normalize_provider("") == "unknown"


# ---------------------------------------------------------------------------
# Child span creation tests
# ---------------------------------------------------------------------------


class TestGenerateStructuredSpans:
    def test_creates_child_span_with_all_attributes(self) -> None:
        adapter = LiteLLMStructuredLLM(model="vllm/meta-llama")
        tracer, exporter = _make_test_tracer()
        mock_litellm = MagicMock()
        mock_litellm.completion.return_value = SimpleNamespace(
            model="vllm/meta-llama-instruct",
            usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7, total_tokens=18),
            _hidden_params={"response_cost": 0.0123},
            choices=[_choice('{"message":"ok"}', finish_reason="stop")],
        )

        with patch.object(
            litellm_adapter_module,
            "_make_span_ctx",
            side_effect=lambda name, **kw: tracer.start_as_current_span(name, attributes=kw.get("attributes", {})),
        ):
            with patch.dict("sys.modules", {"litellm": mock_litellm}):
                result = adapter.generate_structured(
                    messages=[{"role": "user", "content": "hello"}],
                    response_model=_StructuredResponse,
                )

        assert result == _StructuredResponse(message="ok")
        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        span = spans[0]
        attrs = _span_attributes(span)
        assert span.name == "llm.completion"
        assert attrs["llm.request.model"] == "vllm/meta-llama"
        assert attrs["llm.provider"] == "vllm"
        assert attrs["llm.response.model"] == "vllm/meta-llama-instruct"
        assert attrs["llm.prompt_tokens"] == 11
        assert attrs["llm.completion_tokens"] == 7
        assert attrs["llm.total_tokens"] == 18
        assert attrs["llm.cost_usd"] == pytest.approx(0.0123)
        assert attrs["llm.finish_reason"] == "stop"
        assert attrs["llm.status"] == "success"
        assert isinstance(attrs["llm.latency_ms"], (int, float))
        assert attrs["llm.latency_ms"] >= 0
        assert span.status.status_code == StatusCode.UNSET

    def test_records_error_span_on_transport_failure(self) -> None:
        adapter = LiteLLMStructuredLLM(model="anthropic/claude-3")
        tracer, exporter = _make_test_tracer()
        mock_litellm = MagicMock()
        mock_litellm.completion.side_effect = RuntimeError("network down")

        with patch.object(
            litellm_adapter_module,
            "_make_span_ctx",
            side_effect=lambda name, **kw: tracer.start_as_current_span(name, attributes=kw.get("attributes", {})),
        ):
            with patch.dict("sys.modules", {"litellm": mock_litellm}):
                with pytest.raises(StructuredLLMTransportError, match="LLM call failed"):
                    adapter.generate_structured(
                        messages=[{"role": "user", "content": "hello"}],
                        response_model=_StructuredResponse,
                    )

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        span = spans[0]
        attrs = _span_attributes(span)
        assert span.name == "llm.completion"
        assert attrs["llm.request.model"] == "anthropic/claude-3"
        assert attrs["llm.provider"] == "anthropic"
        assert attrs["llm.status"] == "error"
        assert attrs["llm.error.type"] == "RuntimeError"
        assert isinstance(attrs["llm.latency_ms"], (int, float))
        assert span.status.status_code == StatusCode.ERROR

    def test_cost_usd_absent_gracefully_handled(self) -> None:
        adapter = LiteLLMStructuredLLM(model="gpt-4")
        tracer, exporter = _make_test_tracer()
        mock_litellm = MagicMock()
        mock_litellm.completion.return_value = SimpleNamespace(
            model="gpt-4",
            usage=SimpleNamespace(prompt_tokens=2, completion_tokens=3, total_tokens=5),
            _hidden_params={},
            choices=[_choice('{"message":"ok"}', finish_reason="stop")],
        )

        with patch.object(
            litellm_adapter_module,
            "_make_span_ctx",
            side_effect=lambda name, **kw: tracer.start_as_current_span(name, attributes=kw.get("attributes", {})),
        ):
            with patch.dict("sys.modules", {"litellm": mock_litellm}):
                adapter.generate_structured(
                    messages=[{"role": "user", "content": "hello"}],
                    response_model=_StructuredResponse,
                )

        span = exporter.get_finished_spans()[0]
        attrs = _span_attributes(span)
        assert "llm.cost_usd" not in attrs
        assert attrs["llm.status"] == "success"
        assert attrs["llm.prompt_tokens"] == 2
        assert attrs["llm.completion_tokens"] == 3
        assert attrs["llm.total_tokens"] == 5

    def test_usage_as_dict(self) -> None:
        adapter = LiteLLMStructuredLLM(model="gpt-4")
        tracer, exporter = _make_test_tracer()
        mock_litellm = MagicMock()
        mock_litellm.completion.return_value = SimpleNamespace(
            model="gpt-4",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            _hidden_params={"response_cost": 0.001},
            choices=[_choice('{"message":"hi"}', finish_reason="stop")],
        )

        with patch.object(
            litellm_adapter_module,
            "_make_span_ctx",
            side_effect=lambda name, **kw: tracer.start_as_current_span(name, attributes=kw.get("attributes", {})),
        ):
            with patch.dict("sys.modules", {"litellm": mock_litellm}):
                result = adapter.generate_structured(
                    messages=[{"role": "user", "content": "test"}],
                    response_model=_StructuredResponse,
                )

        assert result.message == "hi"
        attrs = _span_attributes(exporter.get_finished_spans()[0])
        assert attrs["llm.prompt_tokens"] == 10
        assert attrs["llm.completion_tokens"] == 5
        assert attrs["llm.total_tokens"] == 15

    def test_no_usage_no_hidden_params(self) -> None:
        adapter = LiteLLMStructuredLLM(model="gpt-4")
        tracer, exporter = _make_test_tracer()
        mock_litellm = MagicMock()
        mock_litellm.completion.return_value = SimpleNamespace(
            model="gpt-4",
            usage=None,
            _hidden_params=None,
            choices=[_choice('{"message":"ok"}', finish_reason="stop")],
        )

        with patch.object(
            litellm_adapter_module,
            "_make_span_ctx",
            side_effect=lambda name, **kw: tracer.start_as_current_span(name, attributes=kw.get("attributes", {})),
        ):
            with patch.dict("sys.modules", {"litellm": mock_litellm}):
                adapter.generate_structured(
                    messages=[{"role": "user", "content": "test"}],
                    response_model=_StructuredResponse,
                )

        attrs = _span_attributes(exporter.get_finished_spans()[0])
        assert "llm.prompt_tokens" not in attrs
        assert "llm.completion_tokens" not in attrs
        assert "llm.total_tokens" not in attrs
        assert "llm.cost_usd" not in attrs
        assert attrs["llm.status"] == "success"

    def test_same_response_model_no_response_model_attr(self) -> None:
        adapter = LiteLLMStructuredLLM(model="gpt-4")
        tracer, exporter = _make_test_tracer()
        mock_litellm = MagicMock()
        mock_litellm.completion.return_value = SimpleNamespace(
            model="gpt-4",
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
            _hidden_params={},
            choices=[_choice('{"message":"ok"}', finish_reason="stop")],
        )

        with patch.object(
            litellm_adapter_module,
            "_make_span_ctx",
            side_effect=lambda name, **kw: tracer.start_as_current_span(name, attributes=kw.get("attributes", {})),
        ):
            with patch.dict("sys.modules", {"litellm": mock_litellm}):
                adapter.generate_structured(
                    messages=[{"role": "user", "content": "test"}],
                    response_model=_StructuredResponse,
                )

        attrs = _span_attributes(exporter.get_finished_spans()[0])
        assert "llm.response.model" not in attrs


# ---------------------------------------------------------------------------
# Response validation tests
# ---------------------------------------------------------------------------


class TestResponseValidation:
    def test_empty_content_raises(self) -> None:
        adapter = LiteLLMStructuredLLM(model="gpt-4")
        mock_litellm = MagicMock()
        mock_litellm.completion.return_value = SimpleNamespace(
            model="gpt-4",
            usage=None,
            _hidden_params=None,
            choices=[SimpleNamespace(message=SimpleNamespace(content=None), finish_reason="stop")],
        )

        with patch.dict("sys.modules", {"litellm": mock_litellm}):
            with pytest.raises(StructuredLLMResponseError, match="LLM returned empty content"):
                adapter.generate_structured(
                    messages=[{"role": "user", "content": "test"}],
                    response_model=_StructuredResponse,
                )

    def test_invalid_json_raises(self) -> None:
        adapter = LiteLLMStructuredLLM(model="gpt-4")
        mock_litellm = MagicMock()
        mock_litellm.completion.return_value = SimpleNamespace(
            model="gpt-4",
            usage=None,
            _hidden_params=None,
            choices=[_choice("not-json", finish_reason="stop")],
        )

        with patch.dict("sys.modules", {"litellm": mock_litellm}):
            with pytest.raises(StructuredLLMResponseError, match="LLM returned invalid JSON"):
                adapter.generate_structured(
                    messages=[{"role": "user", "content": "test"}],
                    response_model=_StructuredResponse,
                )

    def test_schema_validation_failure_raises(self) -> None:
        adapter = LiteLLMStructuredLLM(model="gpt-4")
        mock_litellm = MagicMock()
        mock_litellm.completion.return_value = SimpleNamespace(
            model="gpt-4",
            usage=None,
            _hidden_params=None,
            choices=[_choice('{"wrong_field": 123}', finish_reason="stop")],
        )

        with patch.dict("sys.modules", {"litellm": mock_litellm}):
            with pytest.raises(StructuredLLMResponseError, match="schema validation"):
                adapter.generate_structured(
                    messages=[{"role": "user", "content": "test"}],
                    response_model=_StructuredResponse,
                )


# ---------------------------------------------------------------------------
# Graceful degradation (no-op span) tests
# ---------------------------------------------------------------------------


class TestGracefulDegradation:
    def test_noop_span_set_attribute_is_silent(self) -> None:
        span = _NoOpSpan()
        span.set_attribute("key", "value")

    def test_noop_span_set_status_is_silent(self) -> None:
        span = _NoOpSpan()
        span.set_status("error")

    def test_noop_span_record_exception_is_silent(self) -> None:
        span = _NoOpSpan()
        span.record_exception(RuntimeError("test"))

    def test_generate_structured_works_with_noop_span(self) -> None:
        adapter = LiteLLMStructuredLLM(model="gpt-4")
        mock_litellm = MagicMock()
        mock_litellm.completion.return_value = SimpleNamespace(
            model="gpt-4",
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
            _hidden_params={},
            choices=[_choice('{"message":"ok"}', finish_reason="stop")],
        )

        noop_ctx = litellm_adapter_module._noop_span_ctx

        with patch.object(litellm_adapter_module, "_make_span_ctx", side_effect=lambda name, **kw: noop_ctx()):
            with patch.dict("sys.modules", {"litellm": mock_litellm}):
                result = adapter.generate_structured(
                    messages=[{"role": "user", "content": "test"}],
                    response_model=_StructuredResponse,
                )

        assert result == _StructuredResponse(message="ok")

    def test_generate_structured_error_with_noop_span(self) -> None:
        adapter = LiteLLMStructuredLLM(model="gpt-4")
        mock_litellm = MagicMock()
        mock_litellm.completion.side_effect = RuntimeError("fail")

        noop_ctx = litellm_adapter_module._noop_span_ctx

        with patch.object(litellm_adapter_module, "_make_span_ctx", side_effect=lambda name, **kw: noop_ctx()):
            with patch.dict("sys.modules", {"litellm": mock_litellm}):
                with pytest.raises(StructuredLLMTransportError, match="LLM call failed"):
                    adapter.generate_structured(
                        messages=[{"role": "user", "content": "test"}],
                        response_model=_StructuredResponse,
                    )
