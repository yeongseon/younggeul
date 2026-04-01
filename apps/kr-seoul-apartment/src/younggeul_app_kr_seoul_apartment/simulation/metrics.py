from __future__ import annotations

import os
from typing import Any, Protocol, cast

from ..runtime_version import get_runtime_version

otel_metrics: Any | None

try:
    from opentelemetry import metrics as _otel_metrics

    otel_metrics = _otel_metrics
except ImportError:
    otel_metrics = None

_METER_NAME = "younggeul.simulation"
DEFAULT_APP_LABEL = "kr-seoul-apartment"
_initialized = False
_provider: Any = None


class CounterLike(Protocol):
    def add(self, amount: int | float, attributes: dict[str, str] | None = None) -> None: ...


class UpDownCounterLike(Protocol):
    def add(self, amount: int | float, attributes: dict[str, str] | None = None) -> None: ...


class HistogramLike(Protocol):
    def record(self, amount: int | float, attributes: dict[str, str] | None = None) -> None: ...


class _NoOpCounter:
    def add(self, amount: int | float, attributes: dict[str, str] | None = None) -> None:
        del amount, attributes


class _NoOpUpDownCounter:
    def add(self, amount: int | float, attributes: dict[str, str] | None = None) -> None:
        del amount, attributes


class _NoOpHistogram:
    def record(self, amount: int | float, attributes: dict[str, str] | None = None) -> None:
        del amount, attributes


class _NoOpMeter:
    def create_counter(self, name: str, **kwargs: Any) -> CounterLike:
        del name, kwargs
        return _NoOpCounter()

    def create_up_down_counter(self, name: str, **kwargs: Any) -> UpDownCounterLike:
        del name, kwargs
        return _NoOpUpDownCounter()

    def create_histogram(self, name: str, **kwargs: Any) -> HistogramLike:
        del name, kwargs
        return _NoOpHistogram()


class MeterLike(Protocol):
    def create_counter(self, name: str, **kwargs: Any) -> CounterLike: ...

    def create_up_down_counter(self, name: str, **kwargs: Any) -> UpDownCounterLike: ...

    def create_histogram(self, name: str, **kwargs: Any) -> HistogramLike: ...


_NOOP_METER = _NoOpMeter()

_simulation_runs_total: CounterLike | None = None
_simulation_duration_seconds: HistogramLike | None = None
_simulation_node_duration_seconds: HistogramLike | None = None
_llm_requests_total: CounterLike | None = None
_llm_request_duration_seconds: HistogramLike | None = None
_llm_tokens_total: CounterLike | None = None
_llm_cost_usd_total: CounterLike | None = None
_citation_gate_failures_total: CounterLike | None = None
_simulation_active_runs: UpDownCounterLike | None = None


def _is_enabled() -> bool:
    return os.environ.get("OTEL_ENABLED", "").lower() in ("true", "1", "yes")


def init_metrics() -> None:
    global _initialized, _provider

    if _initialized or not _is_enabled() or otel_metrics is None:
        return

    try:
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import (
            ConsoleMetricExporter,
            MetricExporter,
            PeriodicExportingMetricReader,
        )
        from opentelemetry.sdk.resources import Resource
    except ImportError:
        return

    exporter: MetricExporter
    otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter

            otlp_insecure = os.environ.get("OTEL_EXPORTER_OTLP_INSECURE", "").lower() in ("true", "1", "yes")
            exporter = OTLPMetricExporter(endpoint=otlp_endpoint, insecure=otlp_insecure)
        except ImportError:
            exporter = ConsoleMetricExporter()
    else:
        exporter = ConsoleMetricExporter()

    reader = PeriodicExportingMetricReader(exporter)
    resource = Resource(attributes={"service.name": "younggeul", "service.version": get_runtime_version()})
    provider = MeterProvider(metric_readers=[reader], resource=resource)
    otel_metrics.set_meter_provider(provider)
    _provider = provider
    _initialized = True


def shutdown_metrics() -> None:
    global _initialized, _provider

    if _provider is None:
        return

    try:
        _provider.shutdown()
    except Exception:
        pass
    _provider = None
    _initialized = False


def get_meter() -> MeterLike:
    if otel_metrics is None:
        return _NOOP_METER

    return cast(MeterLike, otel_metrics.get_meter(_METER_NAME))


def metric_attrs(**attrs: str) -> dict[str, str]:
    return {"app": DEFAULT_APP_LABEL, **attrs}


def simulation_runs_total() -> CounterLike:
    global _simulation_runs_total

    if _simulation_runs_total is None:
        _simulation_runs_total = get_meter().create_counter(
            "simulation_runs_total",
            description="Total number of simulation runs",
            unit="{run}",
        )

    counter = _simulation_runs_total
    if counter is None:
        return _NoOpCounter()
    return counter


def simulation_duration_seconds() -> HistogramLike:
    global _simulation_duration_seconds

    if _simulation_duration_seconds is None:
        _simulation_duration_seconds = get_meter().create_histogram(
            "simulation_duration_seconds",
            description="Duration of full simulation runs",
            unit="s",
        )

    histogram = _simulation_duration_seconds
    if histogram is None:
        return _NoOpHistogram()
    return histogram


def simulation_node_duration_seconds() -> HistogramLike:
    global _simulation_node_duration_seconds

    if _simulation_node_duration_seconds is None:
        _simulation_node_duration_seconds = get_meter().create_histogram(
            "simulation_node_duration_seconds",
            description="Duration of simulation node execution",
            unit="s",
        )

    histogram = _simulation_node_duration_seconds
    if histogram is None:
        return _NoOpHistogram()
    return histogram


def llm_requests_total() -> CounterLike:
    global _llm_requests_total

    if _llm_requests_total is None:
        _llm_requests_total = get_meter().create_counter(
            "llm_requests_total",
            description="Total number of LLM requests",
            unit="{request}",
        )

    counter = _llm_requests_total
    if counter is None:
        return _NoOpCounter()
    return counter


def llm_request_duration_seconds() -> HistogramLike:
    global _llm_request_duration_seconds

    if _llm_request_duration_seconds is None:
        _llm_request_duration_seconds = get_meter().create_histogram(
            "llm_request_duration_seconds",
            description="LLM request duration",
            unit="s",
        )

    histogram = _llm_request_duration_seconds
    if histogram is None:
        return _NoOpHistogram()
    return histogram


def llm_tokens_total() -> CounterLike:
    global _llm_tokens_total

    if _llm_tokens_total is None:
        _llm_tokens_total = get_meter().create_counter(
            "llm_tokens_total",
            description="Total number of LLM tokens",
            unit="{token}",
        )

    counter = _llm_tokens_total
    if counter is None:
        return _NoOpCounter()
    return counter


def llm_cost_usd_total() -> CounterLike:
    global _llm_cost_usd_total

    if _llm_cost_usd_total is None:
        _llm_cost_usd_total = get_meter().create_counter(
            "llm_cost_usd_total",
            description="Total LLM cost in USD",
            unit="USD",
        )

    counter = _llm_cost_usd_total
    if counter is None:
        return _NoOpCounter()
    return counter


def citation_gate_failures_total() -> CounterLike:
    global _citation_gate_failures_total

    if _citation_gate_failures_total is None:
        _citation_gate_failures_total = get_meter().create_counter(
            "citation_gate_failures_total",
            description="Total citation gate failures",
            unit="{failure}",
        )

    counter = _citation_gate_failures_total
    if counter is None:
        return _NoOpCounter()
    return counter


def simulation_active_runs() -> UpDownCounterLike:
    global _simulation_active_runs

    if _simulation_active_runs is None:
        _simulation_active_runs = get_meter().create_up_down_counter(
            "simulation_active_runs",
            description="Number of currently running simulations",
            unit="{run}",
        )

    udc = _simulation_active_runs
    if udc is None:
        return _NoOpUpDownCounter()
    return udc
