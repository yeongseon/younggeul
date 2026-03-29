"""Tracing initialization and span helpers for simulation nodes."""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from typing import Any, Iterator

from opentelemetry import trace
from opentelemetry.trace import Span, Status, StatusCode, Tracer

_TRACER_NAME = "younggeul.simulation"
_initialized = False


def _is_enabled() -> bool:
    return os.environ.get("OTEL_ENABLED", "").lower() in ("true", "1", "yes")


def init_tracing() -> None:
    """Initialize OpenTelemetry tracing when OTEL is enabled."""

    global _initialized

    if _initialized or not _is_enabled():
        return

    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter, SpanExporter

    provider = TracerProvider()
    exporter: SpanExporter

    otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

        otlp_insecure = os.environ.get("OTEL_EXPORTER_OTLP_INSECURE", "").lower() in ("true", "1", "yes")
        exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=otlp_insecure)
    else:
        exporter = ConsoleSpanExporter()

    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _initialized = True


def get_tracer() -> Tracer:
    """Return the simulation tracer instance.

    Returns:
        OpenTelemetry tracer for simulation spans.
    """
    return trace.get_tracer(_TRACER_NAME)


@contextmanager
def trace_node(
    node_name: str,
    *,
    run_id: str | None = None,
    round_no: int | None = None,
    attributes: dict[str, Any] | None = None,
) -> Iterator[Span]:
    """Create a tracing span around simulation node execution.

    Args:
        node_name: Name of the node being traced.
        run_id: Optional simulation run identifier.
        round_no: Optional simulation round number.
        attributes: Optional additional span attributes.

    Yields:
        Active span context for the node execution block.
    """
    tracer = get_tracer()
    started_at = time.monotonic()
    status = "ok"

    span_attributes: dict[str, Any] = {"node.name": node_name}
    if run_id is not None:
        span_attributes["simulation.run_id"] = run_id
    if round_no is not None:
        span_attributes["simulation.round_no"] = round_no
    if attributes is not None:
        span_attributes.update(attributes)

    with tracer.start_as_current_span(
        f"simulation.node.{node_name}",
        attributes=span_attributes,
    ) as span:
        try:
            yield span
        except Exception as exc:
            status = "error"
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            raise
        finally:
            elapsed = time.monotonic() - started_at
            try:
                from .metrics import metric_attrs, simulation_node_duration_seconds

                simulation_node_duration_seconds().record(
                    elapsed,
                    attributes=metric_attrs(node=node_name, status=status),
                )
            except Exception:
                pass
