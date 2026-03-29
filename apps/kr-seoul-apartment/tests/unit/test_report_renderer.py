from __future__ import annotations

from importlib import import_module
import re
from datetime import datetime
from typing import Any

import pytest

event_store_module = import_module("younggeul_app_kr_seoul_apartment.simulation.event_store")
graph_state_module = import_module("younggeul_app_kr_seoul_apartment.simulation.graph_state")
report_renderer_module = import_module("younggeul_app_kr_seoul_apartment.simulation.nodes.report_renderer")
report_schema_module = import_module("younggeul_app_kr_seoul_apartment.simulation.schemas.report")
simulation_state_module = import_module("younggeul_core.state.simulation")

InMemoryEventStore = event_store_module.InMemoryEventStore
SimulationGraphState = graph_state_module.SimulationGraphState
seed_graph_state = graph_state_module.seed_graph_state
make_report_renderer_node = report_renderer_module.make_report_renderer_node
RenderedClaimEntry = report_schema_module.RenderedClaimEntry
RenderedReport = report_schema_module.RenderedReport
RenderedSection = report_schema_module.RenderedSection
ReportClaim = simulation_state_module.ReportClaim


def _claim(
    claim_id: str,
    *,
    section: str | None = "summary",
    claim_type: str = "fact",
    statement: str = "A claim",
    metrics: dict[str, object] | None = None,
    evidence_ids: list[str] | None = None,
    gate_status: str = "passed",
    extra_json: dict[str, object] | None = None,
) -> ReportClaim:
    claim_json: dict[str, object] = {
        "type": claim_type,
        "statement": statement,
    }
    if section is not None:
        claim_json["section"] = section
    if metrics is not None:
        claim_json["metrics"] = metrics
    if extra_json is not None:
        claim_json.update(extra_json)

    return ReportClaim(
        claim_id=claim_id,
        claim_json=claim_json,
        evidence_ids=[] if evidence_ids is None else evidence_ids,
        gate_status=gate_status,
        repair_count=0,
    )


def _state(
    *, run_id: str = "run-report-render", round_no: int = 2, claims: list[ReportClaim] | None = None
) -> SimulationGraphState:
    state = seed_graph_state("query", run_id, f"name-{run_id}", "gpt-test")
    state["round_no"] = round_no
    state["report_claims"] = [] if claims is None else claims
    return state


def _rendered_event(store: InMemoryEventStore, run_id: str) -> dict[str, Any]:
    events = store.get_events_by_type(run_id, "REPORT_RENDERED")
    assert len(events) == 1
    return events[0].model_dump(mode="python")


def _normalize_markdown(markdown: str) -> str:
    return re.sub(r"\*\*Generated\*\*: .*", "**Generated**: <ts>", markdown)


def test_renders_multiple_claims_across_sections_with_mixed_gate_statuses() -> None:
    store = InMemoryEventStore()
    node = make_report_renderer_node(store)
    claims = [
        _claim("c-1", section="summary", statement="Summary claim", evidence_ids=["e-1"]),
        _claim("c-2", section="direction", statement="Direction claim", gate_status="failed"),
        _claim("c-3", section="drivers", statement="Drivers claim", evidence_ids=["e-2", "e-3"]),
    ]

    result = node(_state(run_id="run-mixed", claims=claims))
    payload = _rendered_event(store, "run-mixed")["payload"]
    rendered = RenderedReport.model_validate(payload["rendered_report"])

    assert result["warnings"] == ["Claim c-2 failed: failed"]
    assert rendered.total_claims == 3
    assert rendered.passed_claims == 2
    assert rendered.failed_claims == 1
    assert [section.section_key for section in rendered.sections] == ["summary", "drivers"]


def test_orders_known_sections_by_required_priority() -> None:
    store = InMemoryEventStore()
    node = make_report_renderer_node(store)
    claims = [
        _claim("c-1", section="risks"),
        _claim("c-2", section="volume"),
        _claim("c-3", section="summary"),
        _claim("c-4", section="drivers"),
        _claim("c-5", section="direction"),
    ]

    node(_state(run_id="run-order-known", claims=claims))
    payload = _rendered_event(store, "run-order-known")["payload"]
    rendered = RenderedReport.model_validate(payload["rendered_report"])

    assert [section.section_key for section in rendered.sections] == [
        "summary",
        "direction",
        "volume",
        "drivers",
        "risks",
    ]


def test_orders_unknown_sections_alphabetically_after_known_sections() -> None:
    store = InMemoryEventStore()
    node = make_report_renderer_node(store)
    claims = [
        _claim("c-1", section="zeta"),
        _claim("c-2", section="summary"),
        _claim("c-3", section="alpha"),
        _claim("c-4", section="beta"),
    ]

    node(_state(run_id="run-order-unknown", claims=claims))
    payload = _rendered_event(store, "run-order-unknown")["payload"]
    rendered = RenderedReport.model_validate(payload["rendered_report"])

    assert [section.section_key for section in rendered.sections] == ["summary", "alpha", "beta", "zeta"]


def test_passed_and_pending_claims_appear_in_rendered_sections() -> None:
    store = InMemoryEventStore()
    node = make_report_renderer_node(store)
    claims = [
        _claim("c-passed", section="summary", gate_status="passed"),
        _claim("c-failed", section="summary", gate_status="failed"),
        _claim("c-pending", section="summary", gate_status="pending"),
    ]

    node(_state(run_id="run-passed-only", claims=claims))
    payload = _rendered_event(store, "run-passed-only")["payload"]
    rendered = RenderedReport.model_validate(payload["rendered_report"])

    assert rendered.sections[0].claim_count == 2
    assert [entry.claim_id for entry in rendered.sections[0].claims] == ["c-passed", "c-pending"]


def test_only_failed_and_repaired_claims_are_returned_as_warnings() -> None:
    store = InMemoryEventStore()
    node = make_report_renderer_node(store)
    claims = [
        _claim("c-1", gate_status="failed"),
        _claim("c-2", gate_status="pending"),
        _claim("c-3", gate_status="repaired"),
    ]

    result = node(_state(run_id="run-warnings", claims=claims))

    assert result["warnings"] == [
        "Claim c-1 failed: failed",
        "Claim c-3 failed: repaired",
    ]


def test_markdown_includes_expected_headers() -> None:
    store = InMemoryEventStore()
    node = make_report_renderer_node(store)

    node(_state(run_id="run-md-headers", round_no=4, claims=[_claim("c-1", section="summary")]))
    payload = _rendered_event(store, "run-md-headers")["payload"]
    markdown = payload["rendered_report"]["markdown"]

    assert "# Simulation Report" in markdown
    assert "**Run**: run-md-headers" in markdown
    assert "**Round**: 4" in markdown
    assert "**Claims**: 1 passed / 1 total" in markdown
    assert "## Summary" in markdown


def test_markdown_includes_evidence_count_per_claim() -> None:
    store = InMemoryEventStore()
    node = make_report_renderer_node(store)
    claims = [
        _claim("c-1", section="summary", statement="S1", evidence_ids=["e1"]),
        _claim("c-2", section="direction", statement="D1", evidence_ids=["e1", "e2", "e3"]),
    ]

    node(_state(run_id="run-md-evidence", claims=claims))
    payload = _rendered_event(store, "run-md-evidence")["payload"]
    markdown = payload["rendered_report"]["markdown"]

    assert "- S1 [evidence: 1]" in markdown
    assert "- D1 [evidence: 3]" in markdown


def test_empty_claims_renders_header_only_without_sections_or_warnings() -> None:
    store = InMemoryEventStore()
    node = make_report_renderer_node(store)

    result = node(_state(run_id="run-empty", claims=[]))
    payload = _rendered_event(store, "run-empty")["payload"]
    rendered = RenderedReport.model_validate(payload["rendered_report"])

    assert rendered.total_claims == 0
    assert rendered.passed_claims == 0
    assert rendered.failed_claims == 0
    assert rendered.sections == []
    assert "## Warnings" not in rendered.markdown
    assert result["warnings"] == []


def test_missing_run_meta_raises_value_error() -> None:
    store = InMemoryEventStore()
    node = make_report_renderer_node(store)
    state = _state(run_id="run-missing-run-meta", claims=[])
    del state["run_meta"]

    with pytest.raises(ValueError, match="run_meta is required"):
        node(state)


def test_emits_report_rendered_event_type() -> None:
    store = InMemoryEventStore()
    node = make_report_renderer_node(store)

    node(_state(run_id="run-event-type", claims=[_claim("c-1")]))

    events = store.get_events("run-event-type")
    assert len(events) == 1
    assert events[0].event_type == "REPORT_RENDERED"


def test_rendered_report_model_fields_roundtrip_from_event_payload() -> None:
    store = InMemoryEventStore()
    node = make_report_renderer_node(store)

    node(_state(run_id="run-model-fields", round_no=3, claims=[_claim("c-1", metrics={"delta": 1.2})]))
    payload = _rendered_event(store, "run-model-fields")["payload"]
    rendered = RenderedReport.model_validate(payload["rendered_report"])

    assert rendered.run_id == "run-model-fields"
    assert rendered.round_no == 3
    assert isinstance(rendered.rendered_at, datetime)
    assert rendered.total_claims == 1
    assert rendered.passed_claims == 1
    assert rendered.failed_claims == 0
    assert isinstance(rendered.sections[0], RenderedSection)
    assert isinstance(rendered.sections[0].claims[0], RenderedClaimEntry)


def test_markdown_is_deterministic_for_same_input_except_timestamp() -> None:
    store = InMemoryEventStore()
    node = make_report_renderer_node(store)
    claims = [
        _claim("c-1", section="summary", statement="S1", evidence_ids=["e1"]),
        _claim("c-2", section="drivers", statement="S2", evidence_ids=["e2", "e3"]),
    ]

    node(_state(run_id="run-det", claims=claims))
    node(_state(run_id="run-det", claims=claims))
    events = store.get_events_by_type("run-det", "REPORT_RENDERED")

    first_md = events[0].payload["rendered_report"]["markdown"]
    second_md = events[1].payload["rendered_report"]["markdown"]

    assert _normalize_markdown(first_md) == _normalize_markdown(second_md)


def test_unknown_section_title_is_title_cased() -> None:
    store = InMemoryEventStore()
    node = make_report_renderer_node(store)

    node(_state(run_id="run-unknown-title", claims=[_claim("c-1", section="market_signal")]))
    payload = _rendered_event(store, "run-unknown-title")["payload"]
    rendered = RenderedReport.model_validate(payload["rendered_report"])

    assert rendered.sections[0].title == "Market Signal"
    assert "## Market Signal" in rendered.markdown


def test_default_section_is_summary_when_missing_section_key() -> None:
    store = InMemoryEventStore()
    node = make_report_renderer_node(store)

    node(_state(run_id="run-default-section", claims=[_claim("c-1", section=None)]))
    payload = _rendered_event(store, "run-default-section")["payload"]
    rendered = RenderedReport.model_validate(payload["rendered_report"])

    assert [section.section_key for section in rendered.sections] == ["summary"]


def test_statement_falls_back_to_summary_field_when_statement_missing() -> None:
    store = InMemoryEventStore()
    node = make_report_renderer_node(store)
    claim = ReportClaim(
        claim_id="c-1",
        claim_json={"section": "summary", "summary": "Fallback summary", "type": "fact"},
        evidence_ids=[],
        gate_status="passed",
        repair_count=0,
    )

    node(_state(run_id="run-fallback-summary", claims=[claim]))
    payload = _rendered_event(store, "run-fallback-summary")["payload"]
    rendered = RenderedReport.model_validate(payload["rendered_report"])

    assert rendered.sections[0].claims[0].statement == "Fallback summary"


def test_claim_type_defaults_to_unknown_when_missing() -> None:
    store = InMemoryEventStore()
    node = make_report_renderer_node(store)
    claim = ReportClaim(
        claim_id="c-1",
        claim_json={"section": "summary", "statement": "S"},
        evidence_ids=[],
        gate_status="passed",
        repair_count=0,
    )

    node(_state(run_id="run-default-type", claims=[claim]))
    payload = _rendered_event(store, "run-default-type")["payload"]
    rendered = RenderedReport.model_validate(payload["rendered_report"])

    assert rendered.sections[0].claims[0].claim_type == "unknown"


def test_event_payload_includes_summary_fields_and_sections_count() -> None:
    store = InMemoryEventStore()
    node = make_report_renderer_node(store)
    claims = [
        _claim("c-1", section="summary"),
        _claim("c-2", section="drivers"),
        _claim("c-3", section="drivers", gate_status="failed"),
    ]

    node(_state(run_id="run-payload-fields", claims=claims))
    payload = _rendered_event(store, "run-payload-fields")["payload"]

    assert payload["run_id"] == "run-payload-fields"
    assert payload["total_claims"] == 3
    assert payload["passed_claims"] == 2
    assert payload["sections"] == 2
    assert "rendered_report" in payload


def test_return_value_contains_event_ref_and_warnings() -> None:
    store = InMemoryEventStore()
    node = make_report_renderer_node(store)
    claims = [_claim("c-1", gate_status="failed")]

    result = node(_state(run_id="run-return-shape", claims=claims))

    assert len(result["event_refs"]) == 1
    assert isinstance(result["event_refs"][0], str)
    assert result["warnings"] == ["Claim c-1 failed: failed"]


def test_section_claim_count_matches_number_of_claim_entries() -> None:
    store = InMemoryEventStore()
    node = make_report_renderer_node(store)
    claims = [
        _claim("c-1", section="drivers"),
        _claim("c-2", section="drivers"),
        _claim("c-3", section="summary"),
    ]

    node(_state(run_id="run-claim-count", claims=claims))
    payload = _rendered_event(store, "run-claim-count")["payload"]
    rendered = RenderedReport.model_validate(payload["rendered_report"])
    claim_count_by_section = {section.section_key: section.claim_count for section in rendered.sections}

    assert claim_count_by_section == {"summary": 1, "drivers": 2}


@pytest.mark.parametrize(
    ("metrics", "expected"),
    [
        ({"pct": 1.2}, {"pct": 1.2}),
        (None, None),
    ],
)
def test_metrics_field_is_rendered_from_claim_json(
    metrics: dict[str, object] | None,
    expected: dict[str, object] | None,
) -> None:
    store = InMemoryEventStore()
    node = make_report_renderer_node(store)

    node(_state(run_id=f"run-metrics-{expected}", claims=[_claim("c-1", metrics=metrics)]))
    payload = _rendered_event(store, f"run-metrics-{expected}")["payload"]
    rendered = RenderedReport.model_validate(payload["rendered_report"])

    assert rendered.sections[0].claims[0].metrics == expected


def test_markdown_includes_warnings_section_when_any_claim_failed() -> None:
    store = InMemoryEventStore()
    node = make_report_renderer_node(store)
    claims = [_claim("c-1", gate_status="failed")]

    node(_state(run_id="run-md-warnings", claims=claims))
    payload = _rendered_event(store, "run-md-warnings")["payload"]
    markdown = payload["rendered_report"]["markdown"]

    assert "## Warnings" in markdown
    assert "- Claim c-1 failed: failed" in markdown
