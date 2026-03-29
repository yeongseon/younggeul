from __future__ import annotations

from importlib import import_module
from typing import Any

import pytest

event_store_module = import_module("younggeul_app_kr_seoul_apartment.simulation.event_store")
graph_state_module = import_module("younggeul_app_kr_seoul_apartment.simulation.graph_state")
round_summarizer_module = import_module("younggeul_app_kr_seoul_apartment.simulation.nodes.round_summarizer")
simulation_state_module = import_module("younggeul_core.state.simulation")

InMemoryEventStore = event_store_module.InMemoryEventStore
SimulationGraphState = graph_state_module.SimulationGraphState
seed_graph_state = graph_state_module.seed_graph_state
make_round_summarizer_node = round_summarizer_module.make_round_summarizer_node
ParticipantState = simulation_state_module.ParticipantState
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


def _base_state(run_id: str = "summary-run") -> SimulationGraphState:
    state = seed_graph_state("질문", run_id, f"run-{run_id}", "gpt-test")
    state["round_no"] = 2
    state["world"] = {
        "11680": _make_segment(gu_code="11680", gu_name="강남구", current_median_price=2_100_000, current_volume=111),
        "11650": _make_segment(gu_code="11650", gu_name="서초구", current_median_price=1_800_000, current_volume=95),
    }
    state["participants"] = {
        "buyer-0001": _make_participant(participant_id="buyer-0001", role="buyer", capital=1_000, holdings=1),
        "buyer-0002": _make_participant(participant_id="buyer-0002", role="buyer", capital=2_000, holdings=0),
        "investor-0001": _make_participant(participant_id="investor-0001", role="investor", capital=7_000, holdings=3),
    }
    state["warnings"] = ["w1", "w2"]
    return state


def test_emits_simulation_completed_event_and_returns_event_refs() -> None:
    run_id = "emit-event"
    store = InMemoryEventStore()
    node = make_round_summarizer_node(store)

    result = node(_base_state(run_id))
    events = store.get_events_by_type(run_id, "SIMULATION_COMPLETED")

    assert len(events) == 1
    assert result["event_refs"] == [events[0].event_id]


def test_world_summary_contains_per_gu_median_price_and_volume() -> None:
    run_id = "world-summary"
    store = InMemoryEventStore()
    node = make_round_summarizer_node(store)

    node(_base_state(run_id))
    payload = store.get_events_by_type(run_id, "SIMULATION_COMPLETED")[0].payload

    assert payload["world_summary"] == {
        "11650": {"median_price": 1_800_000, "volume": 95},
        "11680": {"median_price": 2_100_000, "volume": 111},
    }


def test_participant_summary_aggregates_by_role() -> None:
    run_id = "participant-summary"
    store = InMemoryEventStore()
    node = make_round_summarizer_node(store)

    node(_base_state(run_id))
    payload = store.get_events_by_type(run_id, "SIMULATION_COMPLETED")[0].payload

    assert payload["participant_summary"] == {
        "buyer": {"count": 2, "total_capital": 3_000, "total_holdings": 1},
        "investor": {"count": 1, "total_capital": 7_000, "total_holdings": 3},
    }


def test_event_payload_has_expected_top_level_fields() -> None:
    run_id = "payload-fields"
    store = InMemoryEventStore()
    node = make_round_summarizer_node(store)

    node(_base_state(run_id))
    payload = store.get_events_by_type(run_id, "SIMULATION_COMPLETED")[0].payload

    assert set(payload.keys()) == {"total_rounds", "world_summary", "participant_summary", "total_warnings"}
    assert payload["total_rounds"] == 2


def test_empty_world_and_participants_produce_empty_summaries() -> None:
    run_id = "empty-state"
    store = InMemoryEventStore()
    node = make_round_summarizer_node(store)
    state = _base_state(run_id)
    state["world"] = {}
    state["participants"] = {}

    node(state)
    payload = store.get_events_by_type(run_id, "SIMULATION_COMPLETED")[0].payload

    assert payload["world_summary"] == {}
    assert payload["participant_summary"] == {}


def test_total_warnings_counts_warning_list_items() -> None:
    run_id = "warning-count"
    store = InMemoryEventStore()
    node = make_round_summarizer_node(store)
    state = _base_state(run_id)
    state["warnings"] = ["w1", "w2", "w3"]

    node(state)
    payload = store.get_events_by_type(run_id, "SIMULATION_COMPLETED")[0].payload

    assert payload["total_warnings"] == 3


def test_non_list_warnings_default_to_zero_total_warnings() -> None:
    run_id = "warning-shape"
    store = InMemoryEventStore()
    node = make_round_summarizer_node(store)
    state = _base_state(run_id)
    raw_state: dict[str, Any] = state
    raw_state["warnings"] = "not-a-list"

    node(state)
    payload = store.get_events_by_type(run_id, "SIMULATION_COMPLETED")[0].payload

    assert payload["total_warnings"] == 0


def test_missing_run_meta_raises_value_error() -> None:
    store = InMemoryEventStore()
    node = make_round_summarizer_node(store)
    state = _base_state("missing-run-meta")
    del state["run_meta"]

    with pytest.raises(ValueError, match="run_meta is required"):
        node(state)
