from importlib import import_module
from unittest.mock import MagicMock, patch

import pytest
from opentelemetry import trace
from opentelemetry.trace import StatusCode

event_store_module = import_module("younggeul_app_kr_seoul_apartment.simulation.event_store")
graph_module = import_module("younggeul_app_kr_seoul_apartment.simulation.graph")
graph_state_module = import_module("younggeul_app_kr_seoul_apartment.simulation.graph_state")
simulation_state_module = import_module("younggeul_core.state.simulation")
tracing_module = import_module("younggeul_app_kr_seoul_apartment.simulation.tracing")

InMemoryEventStore = event_store_module.InMemoryEventStore
ScenarioSpec = simulation_state_module.ScenarioSpec
build_simulation_graph = graph_module.build_simulation_graph
seed_graph_state = graph_state_module.seed_graph_state


def _make_seed(run_id: str, *, max_rounds: int = 1) -> dict[str, object]:
    state: dict[str, object] = seed_graph_state(
        user_query="강남구 아파트 시장 시뮬레이션",
        run_id=run_id,
        run_name=f"run-{run_id}",
        model_id="gpt-test",
    )
    state["max_rounds"] = max_rounds
    return state


def test_trace_node_context_manager_works_when_disabled() -> None:
    with patch.dict("os.environ", {"OTEL_ENABLED": ""}, clear=False):
        marker = []
        with tracing_module.trace_node("intake_planner"):
            marker.append("ok")

    assert marker == ["ok"]


def test_trace_node_captures_run_id_and_round_no() -> None:
    with patch.dict("os.environ", {"OTEL_ENABLED": "true"}, clear=False):
        span = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__enter__.return_value = span
        mock_cm.__exit__.return_value = False
        tracer = MagicMock()
        tracer.start_as_current_span.return_value = mock_cm

        with patch.object(tracing_module, "get_tracer", return_value=tracer):
            with tracing_module.trace_node("scenario_builder", run_id="run-123", round_no=2):
                pass

    _, kwargs = tracer.start_as_current_span.call_args
    assert kwargs["attributes"]["node.name"] == "scenario_builder"
    assert kwargs["attributes"]["simulation.run_id"] == "run-123"
    assert kwargs["attributes"]["simulation.round_no"] == 2


def test_trace_node_records_exception_on_error() -> None:
    with patch.dict("os.environ", {"OTEL_ENABLED": "true"}, clear=False):
        span = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__enter__.return_value = span
        mock_cm.__exit__.return_value = False
        tracer = MagicMock()
        tracer.start_as_current_span.return_value = mock_cm

        with patch.object(tracing_module, "get_tracer", return_value=tracer):
            with pytest.raises(RuntimeError, match="boom"):
                with tracing_module.trace_node("round_resolver"):
                    raise RuntimeError("boom")

    span.record_exception.assert_called_once()
    status = span.set_status.call_args.args[0]
    assert status.status_code == StatusCode.ERROR
    assert status.description == "boom"


def test_get_tracer_returns_tracer() -> None:
    tracer = tracing_module.get_tracer()
    assert isinstance(tracer, trace.Tracer)


def test_init_tracing_is_safe_when_disabled() -> None:
    tracing_module._initialized = False
    with patch.dict("os.environ", {"OTEL_ENABLED": ""}, clear=False):
        tracing_module.init_tracing()

    assert tracing_module._initialized is False


def test_init_tracing_is_idempotent() -> None:
    tracing_module._initialized = False
    with (
        patch.dict("os.environ", {"OTEL_ENABLED": "true"}, clear=False),
        patch("opentelemetry.sdk.trace.TracerProvider") as tracer_provider_cls,
        patch("opentelemetry.sdk.trace.export.BatchSpanProcessor") as batch_processor_cls,
        patch("opentelemetry.sdk.trace.export.ConsoleSpanExporter") as console_exporter_cls,
        patch("opentelemetry.trace.set_tracer_provider") as set_provider,
    ):
        provider = tracer_provider_cls.return_value
        batch_processor = batch_processor_cls.return_value
        console_exporter = console_exporter_cls.return_value

        tracing_module.init_tracing()
        tracing_module.init_tracing()

    tracer_provider_cls.assert_called_once()
    batch_processor_cls.assert_called_once_with(console_exporter)
    provider.add_span_processor.assert_called_once_with(batch_processor)
    set_provider.assert_called_once_with(provider)
    assert tracing_module._initialized is True


def test_graph_runs_with_tracing_wrapper() -> None:
    store = InMemoryEventStore()
    graph = build_simulation_graph(store)

    final = graph.invoke(_make_seed("run-tracing", max_rounds=2))

    assert final["intake_plan"]["planner_status"] == "stub"
    assert isinstance(final["scenario"], ScenarioSpec)
    assert final["round_no"] == 2
