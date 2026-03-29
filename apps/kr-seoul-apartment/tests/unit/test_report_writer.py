from __future__ import annotations

from datetime import date
from importlib import import_module
from typing import Any

import pytest

evidence_builder_module = import_module("younggeul_app_kr_seoul_apartment.simulation.nodes.evidence_builder")
event_store_module = import_module("younggeul_app_kr_seoul_apartment.simulation.event_store")
evidence_store_module = import_module("younggeul_app_kr_seoul_apartment.simulation.evidence.store")
graph_state_module = import_module("younggeul_app_kr_seoul_apartment.simulation.graph_state")
report_writer_module = import_module("younggeul_app_kr_seoul_apartment.simulation.nodes.report_writer")
simulation_state_module = import_module("younggeul_core.state.simulation")

InMemoryEvidenceStore = evidence_store_module.InMemoryEvidenceStore
InMemoryEventStore = event_store_module.InMemoryEventStore
seed_graph_state = graph_state_module.seed_graph_state
make_evidence_builder_node = evidence_builder_module.make_evidence_builder_node
make_report_writer_node = report_writer_module.make_report_writer_node
ParticipantState = simulation_state_module.ParticipantState
RoundOutcome = simulation_state_module.RoundOutcome
ScenarioSpec = simulation_state_module.ScenarioSpec
SegmentState = simulation_state_module.SegmentState
Shock = simulation_state_module.Shock


def _make_segment(**overrides: Any) -> Any:
    payload: dict[str, Any] = {
        "gu_code": "11680",
        "gu_name": "강남구",
        "current_median_price": 2_000_000,
        "current_volume": 100,
        "price_trend": "flat",
        "sentiment_index": 0.6,
        "supply_pressure": 0.0,
    }
    payload.update(overrides)
    return SegmentState(**payload)


def _make_participant(**overrides: Any) -> Any:
    payload: dict[str, Any] = {
        "participant_id": "buyer-001",
        "role": "buyer",
        "capital": 1_000,
        "holdings": 1,
        "sentiment": "neutral",
        "risk_tolerance": 0.5,
    }
    payload.update(overrides)
    return ParticipantState(**payload)


def _make_shock(**overrides: Any) -> Any:
    payload: dict[str, Any] = {
        "shock_type": "interest_rate",
        "description": "Interest rate hike",
        "magnitude": 0.2,
        "target_segments": ["11680"],
    }
    payload.update(overrides)
    return Shock(**payload)


def _make_scenario(**overrides: Any) -> Any:
    payload: dict[str, Any] = {
        "scenario_name": "Report Test",
        "target_gus": ["11680", "11650"],
        "target_period_start": date(2026, 1, 1),
        "target_period_end": date(2026, 12, 31),
        "shocks": [_make_shock()],
    }
    payload.update(overrides)
    return ScenarioSpec(**payload)


def _make_outcome(**overrides: Any) -> Any:
    payload: dict[str, Any] = {
        "round_no": 2,
        "cleared_volume": {"11680": 12, "11650": 8},
        "price_changes": {"11680": 0.02, "11650": -0.01},
        "governance_applied": [],
        "market_actions_resolved": 5,
    }
    payload.update(overrides)
    return RoundOutcome(**payload)


def _base_state(run_id: str = "report-run") -> dict[str, Any]:
    state: dict[str, Any] = seed_graph_state("질문", run_id, f"run-{run_id}", "gpt-test")
    state["round_no"] = 2
    state["world"] = {
        "11680": _make_segment(
            gu_code="11680",
            gu_name="강남구",
            current_median_price=2_200_000,
            current_volume=111,
            price_trend="up",
        ),
        "11650": _make_segment(
            gu_code="11650",
            gu_name="서초구",
            current_median_price=1_850_000,
            current_volume=87,
            price_trend="down",
        ),
    }
    state["participants"] = {
        "buyer-001": _make_participant(participant_id="buyer-001", role="buyer", capital=3_000, holdings=1),
        "investor-001": _make_participant(
            participant_id="investor-001",
            role="investor",
            capital=8_000,
            holdings=5,
        ),
        "tenant-001": _make_participant(participant_id="tenant-001", role="tenant", capital=600, holdings=0),
    }
    state["scenario"] = _make_scenario()
    state["governance_actions"] = {}
    state["last_outcome"] = _make_outcome()
    state["event_refs"] = ["evt-001", "evt-002"]
    return state


def _build_claims(state: dict[str, Any]) -> tuple[list[Any], list[Any], Any, Any]:
    evidence_store = InMemoryEvidenceStore()
    event_store = InMemoryEventStore()
    make_evidence_builder_node(evidence_store)(state)
    result = make_report_writer_node(evidence_store, event_store)(state)
    return result["report_claims"], result["event_refs"], evidence_store, event_store


def _claims_by_type(claims: list[Any]) -> dict[str, list[Any]]:
    grouped: dict[str, list[Any]] = {}
    for claim in claims:
        claim_type = str(claim.claim_json["type"])
        grouped.setdefault(claim_type, []).append(claim)
    return grouped


def test_full_state_produces_at_least_five_claims() -> None:
    claims, _, _, _ = _build_claims(_base_state("at-least-five"))

    assert len(claims) >= 5


def test_expected_claim_types_are_present() -> None:
    claims, _, _, _ = _build_claims(_base_state("types"))
    claim_types = {claim.claim_json["type"] for claim in claims}

    assert claim_types >= {
        "direction",
        "volume",
        "participant_summary",
        "risk_factors",
        "simulation_overview",
    }


def test_claim_json_contract_shape_is_enforced() -> None:
    claims, _, _, _ = _build_claims(_base_state("contract"))

    for claim in claims:
        payload = claim.claim_json
        assert set(payload) == {"type", "section", "subject", "statement", "metrics"}
        assert isinstance(payload["type"], str)
        assert isinstance(payload["section"], str)
        assert isinstance(payload["subject"], str)
        assert isinstance(payload["statement"], str)
        assert payload["metrics"] is None or isinstance(payload["metrics"], dict)


def test_claim_sections_only_use_allowed_values() -> None:
    claims, _, _, _ = _build_claims(_base_state("sections"))
    allowed_sections = {"summary", "direction", "volume", "drivers", "risks"}

    assert {claim.claim_json["section"] for claim in claims} <= allowed_sections


def test_all_evidence_ids_resolve_to_records() -> None:
    claims, _, evidence_store, _ = _build_claims(_base_state("evidence-resolve"))

    for claim in claims:
        assert claim.evidence_ids
        for evidence_id in claim.evidence_ids:
            assert evidence_store.get(evidence_id) is not None


def test_all_claims_start_with_pending_gate_status() -> None:
    claims, _, _, _ = _build_claims(_base_state("pending-status"))

    assert {claim.gate_status for claim in claims} == {"pending"}


def test_all_claims_have_zero_repair_count() -> None:
    claims, _, _, _ = _build_claims(_base_state("repair-count"))

    assert all(claim.repair_count == 0 for claim in claims)


def test_deterministic_output_same_input_same_claim_payloads() -> None:
    state = _base_state("determinism")
    first_claims, _, _, _ = _build_claims(state)
    second_claims, _, _, _ = _build_claims(state)

    def normalized(claims: list[Any]) -> list[tuple[Any, Any, int, Any, int]]:
        return sorted(
            [
                (
                    claim.claim_json["type"],
                    claim.claim_json["subject"],
                    len(claim.evidence_ids),
                    claim.claim_json["statement"],
                    int(claim.claim_json["metrics"]["round_no"]),
                )
                for claim in claims
            ]
        )

    assert normalized(first_claims) == normalized(second_claims)


def test_empty_world_still_emits_simulation_overview_claim() -> None:
    state = _base_state("empty-world")
    state["world"] = {}
    claims, _, _, _ = _build_claims(state)

    assert any(claim.claim_json["type"] == "simulation_overview" for claim in claims)


def test_missing_run_meta_raises_value_error() -> None:
    state = _base_state("missing-run-meta")
    del state["run_meta"]
    evidence_store = InMemoryEvidenceStore()
    make_evidence_builder_node(evidence_store)(_base_state("missing-run-meta-seed"))

    with pytest.raises(ValueError, match="run_meta is required"):
        make_report_writer_node(evidence_store, InMemoryEventStore())(state)


def test_emits_report_written_event_with_all_claim_ids() -> None:
    run_id = "report-event"
    state = _base_state(run_id)
    claims, event_refs, _, event_store = _build_claims(state)

    events = event_store.get_events_by_type(run_id, "REPORT_WRITTEN")
    assert len(events) == 1
    assert event_refs == [events[0].event_id]
    assert events[0].payload["claim_ids"] == [claim.claim_id for claim in claims]


def test_multiple_segments_get_one_direction_claim_per_segment() -> None:
    claims, _, _, _ = _build_claims(_base_state("direction-per-segment"))
    grouped = _claims_by_type(claims)

    assert len(grouped["direction"]) == 2
    assert {claim.claim_json["subject"] for claim in grouped["direction"]} == {"11680", "11650"}


def test_multiple_segments_get_one_volume_claim_per_segment() -> None:
    claims, _, _, _ = _build_claims(_base_state("volume-per-segment"))
    grouped = _claims_by_type(claims)

    assert len(grouped["volume"]) == 2
    assert {claim.claim_json["subject"] for claim in grouped["volume"]} == {"11680", "11650"}


def test_no_shocks_still_produces_risk_factors_claim() -> None:
    state = _base_state("no-shocks")
    state["scenario"] = _make_scenario(shocks=[])
    claims, _, _, _ = _build_claims(state)

    risk_claim = next(claim for claim in claims if claim.claim_json["type"] == "risk_factors")
    assert "No active shocks" in str(risk_claim.claim_json["statement"])
    assert risk_claim.claim_json["metrics"]["shock_count"] == 0


def test_risk_claim_reports_shock_count_when_shocks_exist() -> None:
    state = _base_state("with-shocks")
    state["scenario"] = _make_scenario(
        shocks=[_make_shock(), _make_shock(description="Demand shock", shock_type="demand")]
    )
    claims, _, _, _ = _build_claims(state)

    risk_claim = next(claim for claim in claims if claim.claim_json["type"] == "risk_factors")
    assert risk_claim.claim_json["metrics"]["shock_count"] == 2
    assert "Active shocks" in str(risk_claim.claim_json["statement"])


def test_participant_summary_claims_generated_per_role_group() -> None:
    claims, _, _, _ = _build_claims(_base_state("role-groups"))
    grouped = _claims_by_type(claims)

    assert len(grouped["participant_summary"]) == 3
    assert {claim.claim_json["subject"] for claim in grouped["participant_summary"]} == {
        "role:buyer",
        "role:investor",
        "role:tenant",
    }


def test_participant_summary_metrics_are_aggregated() -> None:
    state = _base_state("participant-metrics")
    state["participants"]["buyer-002"] = _make_participant(
        participant_id="buyer-002",
        role="buyer",
        capital=2_500,
        holdings=2,
    )
    claims, _, _, _ = _build_claims(state)

    buyer_claim = next(
        claim
        for claim in claims
        if claim.claim_json["type"] == "participant_summary" and claim.claim_json["subject"] == "role:buyer"
    )
    assert buyer_claim.claim_json["metrics"]["count"] == 2
    assert buyer_claim.claim_json["metrics"]["total_capital"] == 5_500
    assert buyer_claim.claim_json["metrics"]["total_holdings"] == 3


def test_simulation_overview_metrics_reflect_state_counts() -> None:
    claims, _, _, _ = _build_claims(_base_state("overview-metrics"))

    overview = next(claim for claim in claims if claim.claim_json["type"] == "simulation_overview")
    assert overview.claim_json["metrics"] == {
        "round_no": 2,
        "segment_count": 2,
        "participant_count": 3,
    }


def test_direction_statement_contains_segment_trend() -> None:
    claims, _, _, _ = _build_claims(_base_state("direction-statement"))

    direction_claims = [claim for claim in claims if claim.claim_json["type"] == "direction"]
    assert any("up" in str(claim.claim_json["statement"]) for claim in direction_claims)
    assert any("down" in str(claim.claim_json["statement"]) for claim in direction_claims)


def test_evidence_ids_are_sorted_and_unique_per_claim() -> None:
    claims, _, _, _ = _build_claims(_base_state("sorted-evidence"))

    for claim in claims:
        assert claim.evidence_ids == sorted(claim.evidence_ids)
        assert len(claim.evidence_ids) == len(set(claim.evidence_ids))


@pytest.mark.parametrize(
    ("trend", "expected"),
    [
        ("up", "up"),
        ("down", "down"),
        ("flat", "flat"),
    ],
)
def test_direction_claim_statement_reflects_each_trend(trend: str, expected: str) -> None:
    state = _base_state(f"trend-{trend}")
    state["world"] = {
        "11680": _make_segment(gu_code="11680", gu_name="강남구", price_trend=trend),
    }
    claims, _, _, _ = _build_claims(state)

    direction_claim = next(claim for claim in claims if claim.claim_json["type"] == "direction")
    assert expected in str(direction_claim.claim_json["statement"])


def test_world_empty_and_participants_empty_still_returns_non_empty_claims() -> None:
    state = _base_state("all-empty")
    state["world"] = {}
    state["participants"] = {}
    claims, _, _, _ = _build_claims(state)

    assert len(claims) >= 1
    assert any(claim.claim_json["type"] == "simulation_overview" for claim in claims)
