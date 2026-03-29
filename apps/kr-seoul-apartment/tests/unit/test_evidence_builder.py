from __future__ import annotations

from importlib import import_module
from typing import Any

import pytest

evidence_store_module = import_module("younggeul_app_kr_seoul_apartment.simulation.evidence.store")
graph_state_module = import_module("younggeul_app_kr_seoul_apartment.simulation.graph_state")
evidence_builder_module = import_module("younggeul_app_kr_seoul_apartment.simulation.nodes.evidence_builder")
simulation_state_module = import_module("younggeul_core.state.simulation")

InMemoryEvidenceStore = evidence_store_module.InMemoryEvidenceStore
SimulationGraphState = graph_state_module.SimulationGraphState
seed_graph_state = graph_state_module.seed_graph_state
make_evidence_builder_node = evidence_builder_module.make_evidence_builder_node
ParticipantState = simulation_state_module.ParticipantState
RoundOutcome = simulation_state_module.RoundOutcome
SegmentState = simulation_state_module.SegmentState


def _make_segment(**overrides: Any) -> SegmentState:
    payload: dict[str, Any] = {
        "gu_code": "11680",
        "gu_name": "강남구",
        "current_median_price": 2_000_000,
        "current_volume": 120,
        "price_trend": "flat",
        "sentiment_index": 0.5,
        "supply_pressure": 0.0,
    }
    payload.update(overrides)
    return SegmentState(**payload)


def _make_participant(**overrides: Any) -> ParticipantState:
    payload: dict[str, Any] = {
        "participant_id": "buyer-0001",
        "role": "buyer",
        "capital": 1_000,
        "holdings": 1,
        "sentiment": "neutral",
        "risk_tolerance": 0.5,
    }
    payload.update(overrides)
    return ParticipantState(**payload)


def _make_outcome(**overrides: Any) -> RoundOutcome:
    payload: dict[str, Any] = {
        "round_no": 2,
        "cleared_volume": {"11680": 12, "11650": 8},
        "price_changes": {"11680": 0.01, "11650": -0.01},
        "governance_applied": [],
        "market_actions_resolved": 3,
    }
    payload.update(overrides)
    return RoundOutcome(**payload)


def _base_state(run_id: str = "evidence-run") -> SimulationGraphState:
    state = seed_graph_state("질문", run_id, f"run-{run_id}", "gpt-test")
    state["round_no"] = 2
    state["world"] = {
        "11680": _make_segment(
            gu_code="11680",
            gu_name="강남구",
            current_median_price=2_100_000,
            current_volume=111,
            price_trend="up",
            sentiment_index=0.7,
        ),
        "11650": _make_segment(
            gu_code="11650",
            gu_name="서초구",
            current_median_price=1_800_000,
            current_volume=95,
            price_trend="down",
            sentiment_index=0.45,
        ),
    }
    state["participants"] = {
        "buyer-0001": _make_participant(participant_id="buyer-0001", role="buyer", capital=1_000, holdings=1),
        "buyer-0002": _make_participant(participant_id="buyer-0002", role="buyer", capital=2_000, holdings=0),
        "investor-0001": _make_participant(participant_id="investor-0001", role="investor", capital=7_000, holdings=3),
    }
    state["last_outcome"] = _make_outcome()
    state["event_refs"] = ["evt-001", "evt-002"]
    return state


def test_builder_creates_simulation_fact() -> None:
    store = InMemoryEvidenceStore()
    node = make_evidence_builder_node(store)

    node(_base_state("simulation-fact"))
    simulation_facts = store.get_by_kind("simulation_fact")

    assert len(simulation_facts) == 1
    fact = simulation_facts[0]
    assert fact.subject_type == "simulation"
    assert fact.subject_id == "simulation-fact"
    assert fact.payload == {
        "total_rounds": 2,
        "total_segments": 2,
        "total_participants": 3,
        "completion_reason": "max_rounds",
    }
    assert fact.source_event_ids == ["evt-002"]


def test_builder_creates_segment_facts() -> None:
    store = InMemoryEvidenceStore()
    node = make_evidence_builder_node(store)

    node(_base_state("segment-facts"))
    segment_facts = store.get_by_kind("segment_fact")

    assert len(segment_facts) == 2
    assert {record.subject_id for record in segment_facts} == {"11650", "11680"}
    payload_by_gu = {record.subject_id: record.payload for record in segment_facts}
    assert payload_by_gu["11680"]["final_median_price"] == 2_100_000
    assert payload_by_gu["11680"]["final_volume"] == 111
    assert payload_by_gu["11650"]["final_trend"] == "down"


def test_builder_creates_participant_facts() -> None:
    store = InMemoryEvidenceStore()
    node = make_evidence_builder_node(store)

    node(_base_state("participant-facts"))
    participant_facts = store.get_by_kind("participant_fact")

    assert len(participant_facts) == 2
    payload_by_role = {record.subject_id: record.payload for record in participant_facts}
    assert payload_by_role["buyer"] == {
        "role": "buyer",
        "count": 2,
        "total_capital": 3_000,
        "total_holdings": 1,
    }
    assert payload_by_role["investor"] == {
        "role": "investor",
        "count": 1,
        "total_capital": 7_000,
        "total_holdings": 3,
    }


def test_builder_creates_round_fact() -> None:
    store = InMemoryEvidenceStore()
    node = make_evidence_builder_node(store)

    node(_base_state("round-fact"))
    round_facts = store.get_by_kind("round_fact")

    assert len(round_facts) == 1
    fact = round_facts[0]
    assert fact.subject_type == "round"
    assert fact.subject_id == "round-2"
    assert fact.payload["market_actions_resolved"] == 3
    assert fact.payload["cleared_volume"] == {"11680": 12, "11650": 8}


def test_builder_no_round_fact_when_no_outcome() -> None:
    store = InMemoryEvidenceStore()
    node = make_evidence_builder_node(store)
    state = _base_state("no-round-fact")
    state["last_outcome"] = None

    node(state)

    assert store.get_by_kind("round_fact") == []


def test_builder_returns_evidence_refs() -> None:
    store = InMemoryEvidenceStore()
    node = make_evidence_builder_node(store)

    result = node(_base_state("evidence-refs"))

    assert set(result["evidence_refs"]) == {record.evidence_id for record in store.get_all()}
    assert len(result["evidence_refs"]) == store.count()


def test_builder_empty_world_and_participants() -> None:
    store = InMemoryEvidenceStore()
    node = make_evidence_builder_node(store)
    state = _base_state("empty-world-participants")
    state["world"] = {}
    state["participants"] = {}
    state["last_outcome"] = None

    result = node(state)

    assert store.count() == 1
    assert len(result["evidence_refs"]) == 1
    assert store.get_by_kind("simulation_fact")[0].payload == {
        "total_rounds": 2,
        "total_segments": 0,
        "total_participants": 0,
        "completion_reason": "max_rounds",
    }


def test_builder_evidence_ids_in_store() -> None:
    store = InMemoryEvidenceStore()
    node = make_evidence_builder_node(store)

    result = node(_base_state("ids-in-store"))

    for evidence_id in result["evidence_refs"]:
        assert store.get(evidence_id) is not None


def test_builder_requires_run_meta() -> None:
    store = InMemoryEvidenceStore()
    node = make_evidence_builder_node(store)
    state = _base_state("missing-run-meta")
    del state["run_meta"]

    with pytest.raises(ValueError, match="run_meta is required"):
        node(state)
