from __future__ import annotations

from datetime import date, datetime, timezone
from importlib import import_module
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel

metrics_module = import_module("younggeul_app_kr_seoul_apartment.simulation.metrics")
tracing_module = import_module("younggeul_app_kr_seoul_apartment.simulation.tracing")
litellm_adapter_module = import_module("younggeul_app_kr_seoul_apartment.simulation.llm.litellm_adapter")
citation_gate_module = import_module("younggeul_app_kr_seoul_apartment.simulation.nodes.citation_gate_node")
evidence_store_module = import_module("younggeul_app_kr_seoul_apartment.simulation.evidence.store")
event_store_module = import_module("younggeul_app_kr_seoul_apartment.simulation.event_store")
graph_state_module = import_module("younggeul_app_kr_seoul_apartment.simulation.graph_state")
simulation_state_module = import_module("younggeul_core.state.simulation")

LiteLLMStructuredLLM = litellm_adapter_module.LiteLLMStructuredLLM
StructuredLLMTransportError = litellm_adapter_module.StructuredLLMTransportError
InMemoryEvidenceStore = evidence_store_module.InMemoryEvidenceStore
InMemoryEventStore = event_store_module.InMemoryEventStore
seed_graph_state = graph_state_module.seed_graph_state
SegmentState = simulation_state_module.SegmentState
ScenarioSpec = simulation_state_module.ScenarioSpec
ReportClaim = simulation_state_module.ReportClaim


def _reset_metric_singletons() -> None:
    setattr(metrics_module, "_initialized", False)
    setattr(metrics_module, "_provider", None)
    setattr(metrics_module, "_simulation_runs_total", None)
    setattr(metrics_module, "_simulation_duration_seconds", None)
    setattr(metrics_module, "_simulation_node_duration_seconds", None)
    setattr(metrics_module, "_llm_requests_total", None)
    setattr(metrics_module, "_llm_request_duration_seconds", None)
    setattr(metrics_module, "_llm_tokens_total", None)
    setattr(metrics_module, "_llm_cost_usd_total", None)
    setattr(metrics_module, "_citation_gate_failures_total", None)
    setattr(metrics_module, "_web_requests_total", None)
    setattr(metrics_module, "_web_request_duration_seconds", None)


def _choice(content: str, *, finish_reason: str = "stop") -> SimpleNamespace:
    return SimpleNamespace(message=SimpleNamespace(content=content), finish_reason=finish_reason)


class _StructuredResponse(BaseModel):
    message: str


def test_init_metrics_and_get_meter_work() -> None:
    _reset_metric_singletons()
    with (
        patch.dict("os.environ", {"OTEL_ENABLED": "true"}, clear=False),
        patch("opentelemetry.sdk.metrics.MeterProvider") as meter_provider_cls,
        patch("opentelemetry.sdk.metrics.export.PeriodicExportingMetricReader") as metric_reader_cls,
        patch("opentelemetry.sdk.metrics.export.ConsoleMetricExporter") as exporter_cls,
        patch("opentelemetry.sdk.resources.Resource") as resource_cls,
        patch("opentelemetry.metrics.set_meter_provider") as set_meter_provider,
    ):
        provider = meter_provider_cls.return_value
        reader = metric_reader_cls.return_value
        exporter = exporter_cls.return_value
        resource = resource_cls.return_value

        metrics_module.init_metrics()
        metrics_module.init_metrics()
        meter = metrics_module.get_meter()

    exporter_cls.assert_called_once()
    metric_reader_cls.assert_called_once_with(exporter)
    meter_provider_cls.assert_called_once()
    _, meter_provider_kwargs = meter_provider_cls.call_args
    assert meter_provider_kwargs["metric_readers"] == [reader]
    if resource_cls.call_count > 0:
        resource_cls.assert_called_once_with(attributes={"service.name": "younggeul", "service.version": "0.2.1"})
        assert meter_provider_kwargs.get("resource") is resource
    set_meter_provider.assert_called_once_with(provider)
    assert getattr(metrics_module, "_initialized") is True
    assert meter is not None


def test_all_metrics_record_without_errors() -> None:
    _reset_metric_singletons()
    attrs_app = metrics_module.metric_attrs()
    attrs_ok = metrics_module.metric_attrs(status="ok")
    attrs_node = metrics_module.metric_attrs(node="scenario_builder", status="ok")
    attrs_llm_ok = metrics_module.metric_attrs(provider="openai", model="gpt-4", status="success")
    attrs_llm = metrics_module.metric_attrs(provider="openai", model="gpt-4")
    attrs_prompt = metrics_module.metric_attrs(provider="openai", model="gpt-4", token_type="prompt")

    metrics_module.simulation_runs_total().add(1, attributes=attrs_ok)
    metrics_module.simulation_duration_seconds().record(1.25, attributes=attrs_app)
    metrics_module.simulation_node_duration_seconds().record(0.15, attributes=attrs_node)
    metrics_module.llm_requests_total().add(1, attributes=attrs_llm_ok)
    metrics_module.llm_request_duration_seconds().record(0.42, attributes=attrs_llm)
    metrics_module.llm_tokens_total().add(123, attributes=attrs_prompt)
    metrics_module.llm_cost_usd_total().add(0.01, attributes=attrs_llm)
    metrics_module.citation_gate_failures_total().add(2, attributes=attrs_app)


def test_graceful_degradation_noop_when_otel_missing() -> None:
    _reset_metric_singletons()
    with patch.object(metrics_module, "otel_metrics", None):
        meter = metrics_module.get_meter()
        assert meter is getattr(metrics_module, "_NOOP_METER")

        metrics_module.simulation_runs_total().add(1, attributes=metrics_module.metric_attrs(status="ok"))
        metrics_module.simulation_duration_seconds().record(1.0, attributes=metrics_module.metric_attrs())
        metrics_module.simulation_node_duration_seconds().record(
            0.2,
            attributes=metrics_module.metric_attrs(node="node", status="ok"),
        )
        metrics_module.llm_requests_total().add(
            1,
            attributes=metrics_module.metric_attrs(provider="openai", model="gpt-4", status="success"),
        )
        metrics_module.llm_request_duration_seconds().record(
            0.4,
            attributes=metrics_module.metric_attrs(provider="openai", model="gpt-4"),
        )
        metrics_module.llm_tokens_total().add(
            10,
            attributes=metrics_module.metric_attrs(provider="openai", model="gpt-4", token_type="prompt"),
        )
        metrics_module.llm_cost_usd_total().add(
            0.02,
            attributes=metrics_module.metric_attrs(provider="openai", model="gpt-4"),
        )
        metrics_module.citation_gate_failures_total().add(1, attributes=metrics_module.metric_attrs())


def test_trace_node_emits_duration_metric_with_success_status() -> None:
    mock_histogram = MagicMock()
    span = MagicMock()
    cm = MagicMock()
    cm.__enter__.return_value = span
    cm.__exit__.return_value = False
    tracer = MagicMock()
    tracer.start_as_current_span.return_value = cm

    with (
        patch.object(tracing_module, "get_tracer", return_value=tracer),
        patch(
            "younggeul_app_kr_seoul_apartment.simulation.metrics.simulation_node_duration_seconds",
            return_value=mock_histogram,
        ),
    ):
        with tracing_module.trace_node("scenario_builder"):
            pass

    _, kwargs = mock_histogram.record.call_args
    assert kwargs["attributes"]["app"] == "kr-seoul-apartment"
    assert kwargs["attributes"]["node"] == "scenario_builder"
    assert kwargs["attributes"]["status"] == "ok"


def test_trace_node_emits_duration_metric_with_error_status() -> None:
    mock_histogram = MagicMock()
    span = MagicMock()
    cm = MagicMock()
    cm.__enter__.return_value = span
    cm.__exit__.return_value = False
    tracer = MagicMock()
    tracer.start_as_current_span.return_value = cm

    with (
        patch.object(tracing_module, "get_tracer", return_value=tracer),
        patch(
            "younggeul_app_kr_seoul_apartment.simulation.metrics.simulation_node_duration_seconds",
            return_value=mock_histogram,
        ),
        pytest.raises(RuntimeError, match="boom"),
    ):
        with tracing_module.trace_node("round_resolver"):
            raise RuntimeError("boom")

    _, kwargs = mock_histogram.record.call_args
    assert kwargs["attributes"]["status"] == "error"


def test_generate_structured_emits_llm_metrics_on_success() -> None:
    adapter = LiteLLMStructuredLLM(model="anthropic/claude-3")
    mock_litellm = MagicMock()
    mock_litellm.completion.return_value = SimpleNamespace(
        model="anthropic/claude-3",
        usage={"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
        _hidden_params={"response_cost": 0.015},
        choices=[_choice('{"message":"ok"}')],
    )
    request_counter = MagicMock()
    duration_histogram = MagicMock()
    token_counter = MagicMock()
    cost_counter = MagicMock()

    with (
        patch.object(litellm_adapter_module, "llm_requests_total", return_value=request_counter),
        patch.object(litellm_adapter_module, "llm_request_duration_seconds", return_value=duration_histogram),
        patch.object(litellm_adapter_module, "llm_tokens_total", return_value=token_counter),
        patch.object(litellm_adapter_module, "llm_cost_usd_total", return_value=cost_counter),
        patch.dict("sys.modules", {"litellm": mock_litellm}),
    ):
        result = adapter.generate_structured(
            messages=[{"role": "user", "content": "hello"}],
            response_model=_StructuredResponse,
        )

    assert result.message == "ok"
    request_counter.add.assert_called_once_with(
        1,
        attributes={
            "app": "kr-seoul-apartment",
            "provider": "anthropic",
            "model": "anthropic/claude-3",
            "status": "success",
        },
    )
    duration_histogram.record.assert_called_once()
    token_counter.add.assert_any_call(
        11,
        attributes={
            "app": "kr-seoul-apartment",
            "provider": "anthropic",
            "model": "anthropic/claude-3",
            "token_type": "prompt",
        },
    )
    token_counter.add.assert_any_call(
        7,
        attributes={
            "app": "kr-seoul-apartment",
            "provider": "anthropic",
            "model": "anthropic/claude-3",
            "token_type": "completion",
        },
    )
    cost_counter.add.assert_called_once_with(
        0.015,
        attributes={"app": "kr-seoul-apartment", "provider": "anthropic", "model": "anthropic/claude-3"},
    )


def test_generate_structured_emits_error_metric_on_transport_error() -> None:
    adapter = LiteLLMStructuredLLM(model="gpt-4")
    mock_litellm = MagicMock()
    mock_litellm.completion.side_effect = RuntimeError("network down")
    request_counter = MagicMock()
    duration_histogram = MagicMock()

    with (
        patch.object(litellm_adapter_module, "llm_requests_total", return_value=request_counter),
        patch.object(litellm_adapter_module, "llm_request_duration_seconds", return_value=duration_histogram),
        patch.dict("sys.modules", {"litellm": mock_litellm}),
    ):
        with pytest.raises(StructuredLLMTransportError):
            adapter.generate_structured(
                messages=[{"role": "user", "content": "hello"}],
                response_model=_StructuredResponse,
            )

    request_counter.add.assert_called_once_with(
        1,
        attributes={"app": "kr-seoul-apartment", "provider": "openai", "model": "gpt-4", "status": "error"},
    )
    duration_histogram.record.assert_called_once()


def _build_citation_state(run_id: str) -> dict[str, Any]:
    state: dict[str, Any] = seed_graph_state("질문", run_id, f"run-{run_id}", "gpt-test")
    state["round_no"] = 2
    state["world"] = {
        "11680": SegmentState(
            gu_code="11680",
            gu_name="강남구",
            current_median_price=2_000_000,
            current_volume=100,
            price_trend="flat",
            sentiment_index=0.6,
            supply_pressure=0.0,
        ),
    }
    state["scenario"] = ScenarioSpec(
        scenario_name="Citation Test",
        target_gus=["11680"],
        target_period_start=date(2026, 1, 1),
        target_period_end=date(2026, 12, 31),
        shocks=[],
    )
    return state


def _add_evidence(
    store: Any,
    *,
    evidence_id: str,
    subject_type: str,
    subject_id: str,
    round_no: int = 2,
) -> None:
    record = evidence_store_module.EvidenceRecord(
        evidence_id=evidence_id,
        kind="segment_fact",
        subject_type=subject_type,
        subject_id=subject_id,
        round_no=round_no,
        payload={},
        source_event_ids=[],
        created_at=datetime.now(timezone.utc),
    )
    store.add(record)


def test_citation_gate_emits_failure_counter_when_claims_fail() -> None:
    state = _build_citation_state("metrics-citation-fail")
    state["report_claims"] = [
        ReportClaim(
            claim_id="c-1",
            claim_json={
                "type": "direction",
                "section": "direction",
                "subject": "11680",
                "statement": "deterministic statement",
                "metrics": {"round_no": 2},
            },
            evidence_ids=[],
            gate_status="pending",
            repair_count=0,
        )
    ]
    evidence_store = InMemoryEvidenceStore()
    event_store = InMemoryEventStore()
    failure_counter = MagicMock()

    with patch.object(citation_gate_module, "citation_gate_failures_total", return_value=failure_counter):
        citation_gate_module.make_citation_gate_node(evidence_store, event_store)(state)

    failure_counter.add.assert_called_once_with(1, attributes={"app": "kr-seoul-apartment"})


def test_citation_gate_does_not_emit_failure_counter_when_no_failures() -> None:
    state = _build_citation_state("metrics-citation-pass")
    state["report_claims"] = [
        ReportClaim(
            claim_id="c-1",
            claim_json={
                "type": "direction",
                "section": "direction",
                "subject": "11680",
                "statement": "deterministic statement",
                "metrics": {"round_no": 2},
            },
            evidence_ids=["ev-1"],
            gate_status="pending",
            repair_count=0,
        )
    ]
    evidence_store = InMemoryEvidenceStore()
    _add_evidence(evidence_store, evidence_id="ev-1", subject_type="segment", subject_id="11680")
    event_store = InMemoryEventStore()
    failure_counter = MagicMock()

    with patch.object(citation_gate_module, "citation_gate_failures_total", return_value=failure_counter):
        citation_gate_module.make_citation_gate_node(evidence_store, event_store)(state)

    failure_counter.add.assert_not_called()


def test_shutdown_tracing_is_safe_when_not_initialized() -> None:
    if not hasattr(tracing_module, "shutdown_tracing"):
        return

    setattr(tracing_module, "_initialized", False)
    setattr(tracing_module, "_provider", None)

    tracing_module.shutdown_tracing()


def test_shutdown_metrics_is_safe_when_not_initialized() -> None:
    if not hasattr(metrics_module, "shutdown_metrics"):
        return

    _reset_metric_singletons()

    metrics_module.shutdown_metrics()


def test_shutdown_tracing_flushes_and_shuts_down_provider() -> None:
    if not hasattr(tracing_module, "shutdown_tracing"):
        return

    setattr(tracing_module, "_initialized", False)
    setattr(tracing_module, "_provider", None)

    with (
        patch.dict("os.environ", {"OTEL_ENABLED": "true"}, clear=False),
        patch("opentelemetry.sdk.trace.TracerProvider") as tracer_provider_cls,
        patch("opentelemetry.sdk.trace.export.BatchSpanProcessor"),
        patch("opentelemetry.sdk.trace.export.ConsoleSpanExporter"),
        patch("opentelemetry.sdk.resources.Resource"),
        patch("opentelemetry.trace.set_tracer_provider"),
    ):
        provider = tracer_provider_cls.return_value
        tracing_module.init_tracing()
        tracing_module.shutdown_tracing()

    provider.force_flush.assert_called_once_with()
    provider.shutdown.assert_called_once_with()
    assert getattr(tracing_module, "_provider") is None
    assert getattr(tracing_module, "_initialized") is False


def test_shutdown_metrics_shuts_down_provider() -> None:
    if not hasattr(metrics_module, "shutdown_metrics"):
        return

    _reset_metric_singletons()

    with (
        patch.dict("os.environ", {"OTEL_ENABLED": "true"}, clear=False),
        patch("opentelemetry.sdk.metrics.MeterProvider") as meter_provider_cls,
        patch("opentelemetry.sdk.metrics.export.PeriodicExportingMetricReader"),
        patch("opentelemetry.sdk.metrics.export.ConsoleMetricExporter"),
        patch("opentelemetry.sdk.resources.Resource"),
        patch("opentelemetry.metrics.set_meter_provider"),
    ):
        provider = meter_provider_cls.return_value
        metrics_module.init_metrics()
        metrics_module.shutdown_metrics()

    provider.shutdown.assert_called_once_with()
    assert getattr(metrics_module, "_provider") is None
    assert getattr(metrics_module, "_initialized") is False
