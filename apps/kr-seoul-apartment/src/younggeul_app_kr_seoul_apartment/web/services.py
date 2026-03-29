from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from langgraph.graph.state import CompiledStateGraph
from pydantic import ValidationError

from younggeul_app_kr_seoul_apartment.forecaster import forecast_baseline
from younggeul_app_kr_seoul_apartment.pipeline import BronzeInput, PipelineResult, run_pipeline
from younggeul_app_kr_seoul_apartment.simulation.event_store import InMemoryEventStore
from younggeul_app_kr_seoul_apartment.simulation.evidence.store import InMemoryEvidenceStore
from younggeul_app_kr_seoul_apartment.simulation.events import EventStore
from younggeul_app_kr_seoul_apartment.simulation.graph import build_simulation_graph
from younggeul_app_kr_seoul_apartment.simulation.graph_state import SimulationGraphState, seed_graph_state
from younggeul_app_kr_seoul_apartment.simulation.schemas.report import RenderedReport
from younggeul_app_kr_seoul_apartment.snapshot import publish_snapshot, resolve_snapshot
from younggeul_core.state.gold import BaselineForecast, GoldDistrictMonthlyMetrics
from younggeul_core.state.simulation import ReportClaim
from younggeul_core.state.simulation import SnapshotRef
from younggeul_core.storage.snapshot import SnapshotManifest

from .run_store import RunStore

logger = logging.getLogger(__name__)


def run_pipeline_service(bronze: BronzeInput) -> PipelineResult:
    return run_pipeline(bronze)


def publish_snapshot_service(gold_rows: list[GoldDistrictMonthlyMetrics], base_dir: Path) -> SnapshotRef:
    return publish_snapshot(gold_rows, base_dir)


def resolve_snapshot_service(
    snapshot_id: str, base_dir: Path
) -> tuple[SnapshotManifest, list[GoldDistrictMonthlyMetrics]]:
    return resolve_snapshot(snapshot_id, base_dir)


def forecast_baseline_service(metrics: list[GoldDistrictMonthlyMetrics]) -> list[BaselineForecast]:
    return forecast_baseline(metrics)


def build_simulation_graph_service(event_store: EventStore) -> CompiledStateGraph[Any, Any, Any, Any]:
    return build_simulation_graph(event_store)


def seed_graph_state_service(user_query: str, run_id: str, run_name: str, model_id: str) -> SimulationGraphState:
    return seed_graph_state(user_query, run_id=run_id, run_name=run_name, model_id=model_id)


def run_simulation_background(run_store: RunStore, run_id: str, query: str, max_rounds: int, model_id: str) -> None:
    """Execute simulation in background thread, updating RunStore on completion/failure."""
    try:
        run_store.update_status(run_id, "running")
        event_store = InMemoryEventStore()
        evidence_store = InMemoryEvidenceStore()
        graph = build_simulation_graph(event_store, evidence_store=evidence_store)
        initial_state = seed_graph_state(query, run_id=run_id, run_name=f"web-{run_id[:8]}", model_id=model_id)
        initial_state["max_rounds"] = max_rounds
        final_state = graph.invoke(initial_state)

        report = _extract_report_text(final_state, event_store, run_id)
        run_store.update_status(run_id, "completed", report=report)
    except Exception as exc:
        logger.exception("Simulation %s failed", run_id)
        run_store.update_status(run_id, "failed", error=str(exc))


def _extract_report_text(final_state: dict[str, Any], event_store: InMemoryEventStore, run_id: str) -> str:
    rendered = final_state.get("rendered_report")
    if isinstance(rendered, RenderedReport):
        return rendered.markdown
    if isinstance(rendered, dict):
        try:
            return RenderedReport.model_validate(rendered).markdown
        except ValidationError:
            pass

    rendered_events = event_store.get_events_by_type(run_id, "REPORT_RENDERED")
    if rendered_events:
        payload = rendered_events[-1].payload.get("rendered_report")
        if payload is not None:
            try:
                return RenderedReport.model_validate(payload).markdown
            except ValidationError:
                pass

    report_claims = final_state.get("report_claims")
    if isinstance(report_claims, list) and report_claims:
        lines: list[str] = ["# Simulation Report", ""]
        for claim in report_claims:
            if isinstance(claim, ReportClaim):
                statement = claim.claim_json.get("statement") or claim.claim_json.get("summary") or ""
            elif isinstance(claim, dict):
                claim_json = claim.get("claim_json")
                if isinstance(claim_json, dict):
                    statement = claim_json.get("statement") or claim_json.get("summary") or ""
                else:
                    statement = ""
            else:
                statement = ""
            if statement:
                lines.append(f"- {statement}")

        if len(lines) > 2:
            return "\n".join(lines)

    raise ValueError("Simulation did not produce a rendered report")
