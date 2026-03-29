from __future__ import annotations

from datetime import date, datetime, timezone
from importlib import import_module
from typing import Any

import pytest

evidence_store_module = import_module("younggeul_app_kr_seoul_apartment.simulation.evidence.store")
event_store_module = import_module("younggeul_app_kr_seoul_apartment.simulation.event_store")
graph_state_module = import_module("younggeul_app_kr_seoul_apartment.simulation.graph_state")
citation_gate_module = import_module("younggeul_app_kr_seoul_apartment.simulation.nodes.citation_gate_node")
simulation_state_module = import_module("younggeul_core.state.simulation")

EvidenceRecord = evidence_store_module.EvidenceRecord
InMemoryEvidenceStore = evidence_store_module.InMemoryEvidenceStore
InMemoryEventStore = event_store_module.InMemoryEventStore
seed_graph_state = graph_state_module.seed_graph_state
make_citation_gate_node = citation_gate_module.make_citation_gate_node
ReportClaim = simulation_state_module.ReportClaim
ScenarioSpec = simulation_state_module.ScenarioSpec
SegmentState = simulation_state_module.SegmentState


def _make_state(run_id: str = "citation-run") -> dict[str, Any]:
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


def _add_record(
    store: Any,
    *,
    evidence_id: str,
    kind: str,
    subject_type: str,
    subject_id: str,
    round_no: int = 2,
) -> Any:
    record = EvidenceRecord(
        evidence_id=evidence_id,
        kind=kind,
        subject_type=subject_type,
        subject_id=subject_id,
        round_no=round_no,
        payload={},
        source_event_ids=[],
        created_at=datetime.now(timezone.utc),
    )
    store.add(record)
    return record


def _claim(
    *,
    claim_id: str,
    subject: str = "11680",
    evidence_ids: list[str] | None = None,
    claim_type: str = "direction",
) -> Any:
    return ReportClaim(
        claim_id=claim_id,
        claim_json={
            "type": claim_type,
            "section": "direction",
            "subject": subject,
            "statement": "deterministic statement",
            "metrics": {"round_no": 2},
        },
        evidence_ids=[] if evidence_ids is None else evidence_ids,
        gate_status="pending",
        repair_count=0,
    )


def test_all_claims_pass_when_evidence_ids_are_valid() -> None:
    state = _make_state("all-pass")
    evidence_store = InMemoryEvidenceStore()
    event_store = InMemoryEventStore()
    _add_record(
        evidence_store, evidence_id="ev-segment", kind="segment_fact", subject_type="segment", subject_id="11680"
    )
    state["report_claims"] = [_claim(claim_id="c-1", evidence_ids=["ev-segment"])]

    result = make_citation_gate_node(evidence_store, event_store)(state)
    payload = event_store.get_events_by_type("all-pass", "CITATION_GATE")[0].payload

    assert result["warnings"] == []
    assert payload == {"total_claims": 1, "passed": 1, "failed": 0, "failed_claim_ids": []}


def test_claim_fails_when_evidence_ids_empty() -> None:
    state = _make_state("empty-evidence-ids")
    evidence_store = InMemoryEvidenceStore()
    event_store = InMemoryEventStore()
    state["report_claims"] = [_claim(claim_id="c-1", evidence_ids=[])]

    result = make_citation_gate_node(evidence_store, event_store)(state)
    payload = event_store.get_events_by_type("empty-evidence-ids", "CITATION_GATE")[0].payload

    assert len(result["warnings"]) == 1
    assert "missing evidence_ids" in result["warnings"][0]
    assert payload["failed"] == 1
    assert payload["failed_claim_ids"] == ["c-1"]


def test_claim_fails_when_any_evidence_id_not_found() -> None:
    state = _make_state("missing-evidence")
    evidence_store = InMemoryEvidenceStore()
    event_store = InMemoryEventStore()
    state["report_claims"] = [_claim(claim_id="c-1", evidence_ids=["ev-missing"])]

    result = make_citation_gate_node(evidence_store, event_store)(state)

    assert "missing evidence record" in result["warnings"][0]


def test_mixed_pass_fail_claims() -> None:
    state = _make_state("mixed")
    evidence_store = InMemoryEvidenceStore()
    event_store = InMemoryEventStore()
    _add_record(evidence_store, evidence_id="ev-good", kind="segment_fact", subject_type="segment", subject_id="11680")
    state["report_claims"] = [
        _claim(claim_id="c-pass", evidence_ids=["ev-good"]),
        _claim(claim_id="c-fail", evidence_ids=["ev-missing"]),
    ]

    result = make_citation_gate_node(evidence_store, event_store)(state)
    payload = event_store.get_events_by_type("mixed", "CITATION_GATE")[0].payload

    assert len(result["warnings"]) == 1
    assert payload["total_claims"] == 2
    assert payload["passed"] == 1
    assert payload["failed"] == 1
    assert payload["failed_claim_ids"] == ["c-fail"]


def test_event_payload_counts_are_correct() -> None:
    state = _make_state("event-counts")
    evidence_store = InMemoryEvidenceStore()
    event_store = InMemoryEventStore()
    _add_record(evidence_store, evidence_id="ev-1", kind="segment_fact", subject_type="segment", subject_id="11680")
    _add_record(evidence_store, evidence_id="ev-2", kind="segment_fact", subject_type="segment", subject_id="11680")
    state["report_claims"] = [
        _claim(claim_id="c-1", evidence_ids=["ev-1"]),
        _claim(claim_id="c-2", evidence_ids=["ev-2"]),
        _claim(claim_id="c-3", evidence_ids=[]),
    ]

    make_citation_gate_node(evidence_store, event_store)(state)
    payload = event_store.get_events_by_type("event-counts", "CITATION_GATE")[0].payload

    assert payload == {"total_claims": 3, "passed": 2, "failed": 1, "failed_claim_ids": ["c-3"]}


def test_warnings_contain_claim_id_and_reason() -> None:
    state = _make_state("warning-content")
    evidence_store = InMemoryEvidenceStore()
    event_store = InMemoryEventStore()
    state["report_claims"] = [_claim(claim_id="claim-xyz", evidence_ids=[])]

    result = make_citation_gate_node(evidence_store, event_store)(state)

    assert result["warnings"] == ["claim_id=claim-xyz: missing evidence_ids"]


def test_missing_run_meta_raises_value_error() -> None:
    state = _make_state("missing-run-meta")
    del state["run_meta"]

    with pytest.raises(ValueError, match="run_meta is required"):
        make_citation_gate_node(InMemoryEvidenceStore(), InMemoryEventStore())(state)


def test_empty_report_claims_emits_event_without_errors() -> None:
    state = _make_state("empty-claims")
    state["report_claims"] = []
    evidence_store = InMemoryEvidenceStore()
    event_store = InMemoryEventStore()

    result = make_citation_gate_node(evidence_store, event_store)(state)
    payload = event_store.get_events_by_type("empty-claims", "CITATION_GATE")[0].payload

    assert result["warnings"] == []
    assert payload == {"total_claims": 0, "passed": 0, "failed": 0, "failed_claim_ids": []}


def test_node_does_not_return_report_claims_key() -> None:
    state = _make_state("no-report-claims-return")
    evidence_store = InMemoryEvidenceStore()
    event_store = InMemoryEventStore()
    _add_record(evidence_store, evidence_id="ev-1", kind="segment_fact", subject_type="segment", subject_id="11680")
    state["report_claims"] = [_claim(claim_id="c-1", evidence_ids=["ev-1"])]

    result = make_citation_gate_node(evidence_store, event_store)(state)

    assert "report_claims" not in result


def test_subject_mismatch_fails_claim() -> None:
    state = _make_state("subject-mismatch")
    evidence_store = InMemoryEvidenceStore()
    event_store = InMemoryEventStore()
    _add_record(evidence_store, evidence_id="ev-1", kind="segment_fact", subject_type="segment", subject_id="11650")
    state["report_claims"] = [_claim(claim_id="c-1", subject="11680", evidence_ids=["ev-1"])]

    result = make_citation_gate_node(evidence_store, event_store)(state)

    assert "subject mismatch with evidence" in result["warnings"][0]


def test_round_context_mismatch_fails_claim() -> None:
    state = _make_state("round-mismatch")
    evidence_store = InMemoryEvidenceStore()
    event_store = InMemoryEventStore()
    _add_record(
        evidence_store,
        evidence_id="ev-1",
        kind="segment_fact",
        subject_type="segment",
        subject_id="11680",
        round_no=1,
    )
    state["report_claims"] = [_claim(claim_id="c-1", evidence_ids=["ev-1"])]

    result = make_citation_gate_node(evidence_store, event_store)(state)

    assert "no evidence for round_no=2" in result["warnings"][0]


def test_simulation_subject_passes_when_run_id_matches_evidence() -> None:
    run_id = "simulation-subject"
    state = _make_state(run_id)
    evidence_store = InMemoryEvidenceStore()
    event_store = InMemoryEventStore()
    _add_record(
        evidence_store,
        evidence_id="ev-sim",
        kind="simulation_fact",
        subject_type="simulation",
        subject_id=run_id,
    )
    state["report_claims"] = [
        _claim(claim_id="c-1", subject="simulation", evidence_ids=["ev-sim"], claim_type="simulation_overview")
    ]

    result = make_citation_gate_node(evidence_store, event_store)(state)
    payload = event_store.get_events_by_type(run_id, "CITATION_GATE")[0].payload

    assert result["warnings"] == []
    assert payload["passed"] == 1


def test_role_subject_passes_with_participant_role_evidence() -> None:
    state = _make_state("role-pass")
    evidence_store = InMemoryEvidenceStore()
    event_store = InMemoryEventStore()
    _add_record(
        evidence_store,
        evidence_id="ev-role",
        kind="participant_fact",
        subject_type="participant_role",
        subject_id="buyer",
    )
    state["report_claims"] = [
        _claim(claim_id="c-1", subject="role:buyer", evidence_ids=["ev-role"], claim_type="participant_summary")
    ]

    result = make_citation_gate_node(evidence_store, event_store)(state)

    assert result["warnings"] == []


def test_segment_subject_passes_when_world_contains_segment() -> None:
    state = _make_state("segment-pass")
    evidence_store = InMemoryEvidenceStore()
    event_store = InMemoryEventStore()
    _add_record(evidence_store, evidence_id="ev-seg", kind="segment_fact", subject_type="segment", subject_id="11680")
    state["report_claims"] = [_claim(claim_id="c-1", subject="11680", evidence_ids=["ev-seg"])]

    result = make_citation_gate_node(evidence_store, event_store)(state)

    assert result["warnings"] == []


def test_claim_without_string_subject_skips_subject_check() -> None:
    state = _make_state("non-string-subject")
    evidence_store = InMemoryEvidenceStore()
    event_store = InMemoryEventStore()
    _add_record(evidence_store, evidence_id="ev-1", kind="segment_fact", subject_type="segment", subject_id="11680")
    state["report_claims"] = [
        ReportClaim(
            claim_id="c-1",
            claim_json={
                "type": "direction",
                "section": "direction",
                "subject": {"complex": "object"},
                "statement": "statement",
                "metrics": {"round_no": 2},
            },
            evidence_ids=["ev-1"],
            gate_status="pending",
            repair_count=0,
        )
    ]

    result = make_citation_gate_node(evidence_store, event_store)(state)

    assert result["warnings"] == []


def test_event_ref_matches_emitted_event_id() -> None:
    run_id = "event-ref"
    state = _make_state(run_id)
    evidence_store = InMemoryEvidenceStore()
    event_store = InMemoryEventStore()
    _add_record(evidence_store, evidence_id="ev-1", kind="segment_fact", subject_type="segment", subject_id="11680")
    state["report_claims"] = [_claim(claim_id="c-1", evidence_ids=["ev-1"])]

    result = make_citation_gate_node(evidence_store, event_store)(state)
    event = event_store.get_events_by_type(run_id, "CITATION_GATE")[0]

    assert result["event_refs"] == [event.event_id]


@pytest.mark.parametrize(
    ("subject", "subject_type", "subject_id", "expected_failed"),
    [
        ("role:investor", "participant_role", "investor", 0),
        ("role:investor", "participant_role", "buyer", 1),
        ("simulation", "simulation", "param-subject", 0),
    ],
)
def test_subject_matching_rules(
    subject: str,
    subject_type: str,
    subject_id: str,
    expected_failed: int,
) -> None:
    run_id = "param-subject"
    state = _make_state(run_id)
    evidence_store = InMemoryEvidenceStore()
    event_store = InMemoryEventStore()
    _add_record(
        evidence_store,
        evidence_id="ev-1",
        kind="participant_fact",
        subject_type=subject_type,
        subject_id=subject_id,
    )
    state["report_claims"] = [_claim(claim_id="c-1", subject=subject, evidence_ids=["ev-1"])]

    make_citation_gate_node(evidence_store, event_store)(state)
    payload = event_store.get_events_by_type(run_id, "CITATION_GATE")[0].payload

    assert payload["failed"] == expected_failed
