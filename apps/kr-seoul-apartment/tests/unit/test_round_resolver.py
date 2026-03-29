from __future__ import annotations

# pyright: reportMissingImports=false

from datetime import date, datetime, timezone
from typing import Any

import pytest

from younggeul_app_kr_seoul_apartment.simulation.event_store import InMemoryEventStore
from younggeul_app_kr_seoul_apartment.simulation.graph_state import SimulationGraphState
from younggeul_app_kr_seoul_apartment.simulation.graph_state import seed_graph_state
from younggeul_app_kr_seoul_apartment.simulation.nodes.round_resolver import make_round_resolver_node
from younggeul_app_kr_seoul_apartment.simulation.schemas.round import RoundResolvedPayload
from younggeul_core.state.simulation import ActionProposal, ParticipantState, RoundOutcome, ScenarioSpec, SegmentState


def _make_scenario(**overrides: Any) -> ScenarioSpec:
    payload: dict[str, Any] = {
        "scenario_name": "Resolver Test",
        "target_gus": ["11680", "11650"],
        "target_period_start": date(2026, 1, 1),
        "target_period_end": date(2026, 6, 1),
        "shocks": [],
    }
    payload.update(overrides)
    return ScenarioSpec(**payload)


def _make_segment(**overrides: Any) -> SegmentState:
    payload: dict[str, Any] = {
        "gu_code": "11680",
        "gu_name": "강남구",
        "current_median_price": 1_000,
        "current_volume": 100,
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
        "capital": 10_000,
        "holdings": 0,
        "sentiment": "neutral",
        "risk_tolerance": 0.5,
    }
    payload.update(overrides)
    return ParticipantState(**payload)


def _make_action(**overrides: Any) -> ActionProposal:
    payload: dict[str, Any] = {
        "agent_id": "buyer-0001",
        "round_no": 1,
        "action_type": "buy",
        "target_segment": "11680",
        "confidence": 1.0,
        "reasoning_summary": "test",
    }
    payload.update(overrides)
    return ActionProposal(**payload)


def _base_state(run_id: str = "resolver-run") -> SimulationGraphState:
    state = seed_graph_state("질문", run_id, f"run-{run_id}", "gpt-test")
    state["round_no"] = 3
    state["scenario"] = _make_scenario()
    state["world"] = {
        "11680": _make_segment(gu_code="11680", gu_name="강남구"),
        "11650": _make_segment(gu_code="11650", gu_name="서초구", current_median_price=2_000, current_volume=40),
    }
    state["participants"] = {
        "buyer-0001": _make_participant(participant_id="buyer-0001", role="buyer", capital=10_000, holdings=0),
        "buyer-0002": _make_participant(participant_id="buyer-0002", role="buyer", capital=10_000, holdings=0),
        "seller-0001": _make_participant(participant_id="seller-0001", role="investor", capital=5_000, holdings=3),
        "seller-0002": _make_participant(participant_id="seller-0002", role="investor", capital=5_000, holdings=0),
    }
    state["market_actions"] = {}
    state["last_outcome"] = None
    return state


def test_buy_only_price_goes_up_and_buyer_capital_decreases() -> None:
    store = InMemoryEventStore()
    node = make_round_resolver_node(store)
    state = _base_state("buy-only")
    state["participants"] = {
        "buyer-0001": _make_participant(participant_id="buyer-0001", role="buyer", capital=2_000, holdings=0)
    }
    state["market_actions"] = {
        "buyer-0001": _make_action(agent_id="buyer-0001", action_type="buy", confidence=1.0),
    }

    result = node(state)

    assert result["world"]["11680"].current_median_price == 1_050
    assert result["world"]["11680"].price_trend == "up"
    assert result["participants"]["buyer-0001"].capital == 950
    assert result["participants"]["buyer-0001"].holdings == 1


def test_sell_only_price_goes_down_and_no_transactions_when_no_buyers() -> None:
    store = InMemoryEventStore()
    node = make_round_resolver_node(store)
    state = _base_state("sell-only")
    state["market_actions"] = {
        "seller-0001": _make_action(agent_id="seller-0001", action_type="sell", confidence=1.0),
    }

    result = node(state)

    assert result["world"]["11680"].current_median_price == 950
    assert result["world"]["11680"].price_trend == "down"
    assert result["last_outcome"].market_actions_resolved == 0
    assert result["participants"]["seller-0001"].capital == 5_000


def test_mixed_buy_sell_partial_matching_and_price_movement() -> None:
    store = InMemoryEventStore()
    node = make_round_resolver_node(store)
    state = _base_state("mixed")
    state["market_actions"] = {
        "buyer-0001": _make_action(agent_id="buyer-0001", action_type="buy", confidence=1.0),
        "buyer-0002": _make_action(agent_id="buyer-0002", action_type="buy", confidence=1.0),
        "seller-0001": _make_action(agent_id="seller-0001", action_type="sell", confidence=0.5),
    }

    result = node(state)

    assert result["world"]["11680"].current_median_price == 1_025
    assert result["last_outcome"].cleared_volume["11680"] == 1
    assert result["participants"]["seller-0001"].holdings == 2


@pytest.mark.parametrize(
    ("participant_id", "action_type", "confidence", "expected_pct"),
    [
        ("buyer-0001", "buy", 1.0, 0.05),
        ("seller-0001", "sell", 1.0, -0.05),
    ],
)
def test_price_change_clamped_at_boundaries(
    participant_id: str, action_type: str, confidence: float, expected_pct: float
) -> None:
    store = InMemoryEventStore()
    node = make_round_resolver_node(store)
    state = _base_state(f"clamp-{expected_pct}")
    state["market_actions"] = {
        participant_id: _make_action(agent_id=participant_id, action_type=action_type, confidence=confidence),
    }

    result = node(state)

    assert result["last_outcome"].price_changes["11680"] == pytest.approx(expected_pct)


def test_zero_actions_no_state_change_and_zero_transactions() -> None:
    store = InMemoryEventStore()
    node = make_round_resolver_node(store)
    state = _base_state("zero-actions")
    original_world = state["world"]
    original_participants = state["participants"]

    result = node(state)

    assert result["world"] == original_world
    assert result["participants"] == original_participants
    assert result["last_outcome"] == RoundOutcome(
        round_no=3,
        cleared_volume={},
        price_changes={},
        governance_applied=[],
        market_actions_resolved=0,
    )


def test_missing_market_actions_treated_as_empty() -> None:
    store = InMemoryEventStore()
    node = make_round_resolver_node(store)
    state = _base_state("missing-actions")
    del state["market_actions"]

    result = node(state)

    assert result["last_outcome"].market_actions_resolved == 0
    assert result["last_outcome"].cleared_volume == {}


def test_multiple_segments_resolved_independently() -> None:
    store = InMemoryEventStore()
    node = make_round_resolver_node(store)
    state = _base_state("multi-segment")
    state["participants"]["buyer-0003"] = _make_participant(participant_id="buyer-0003", role="buyer", capital=10_000)
    state["participants"]["seller-0003"] = _make_participant(
        participant_id="seller-0003", role="investor", capital=5_000, holdings=2
    )
    state["market_actions"] = {
        "buyer-0001": _make_action(agent_id="buyer-0001", action_type="buy", target_segment="11680", confidence=1.0),
        "seller-0001": _make_action(agent_id="seller-0001", action_type="sell", target_segment="11680", confidence=0.2),
        "buyer-0003": _make_action(agent_id="buyer-0003", action_type="buy", target_segment="11650", confidence=0.2),
        "seller-0003": _make_action(agent_id="seller-0003", action_type="sell", target_segment="11650", confidence=1.0),
    }

    result = node(state)

    assert set(result["last_outcome"].price_changes.keys()) == {"11680", "11650"}
    assert result["world"]["11680"].current_median_price != state["world"]["11680"].current_median_price
    assert result["world"]["11650"].current_median_price != state["world"]["11650"].current_median_price


def test_matching_respects_capital_constraint() -> None:
    store = InMemoryEventStore()
    node = make_round_resolver_node(store)
    state = _base_state("capital-constraint")
    state["world"] = {
        "11680": _make_segment(current_median_price=1_500, current_volume=0),
        "11650": state["world"]["11650"],
    }
    state["participants"]["buyer-0001"] = _make_participant(participant_id="buyer-0001", role="buyer", capital=1_000)
    state["market_actions"] = {
        "buyer-0001": _make_action(agent_id="buyer-0001", action_type="buy", confidence=1.0),
        "seller-0001": _make_action(agent_id="seller-0001", action_type="sell", confidence=1.0),
    }

    result = node(state)

    assert result["last_outcome"].market_actions_resolved == 0
    assert result["participants"]["buyer-0001"].capital == 1_000
    assert result["participants"]["seller-0001"].holdings == 3


def test_matching_respects_holdings_constraint() -> None:
    store = InMemoryEventStore()
    node = make_round_resolver_node(store)
    state = _base_state("holdings-constraint")
    state["world"] = {
        "11680": _make_segment(current_volume=0),
        "11650": state["world"]["11650"],
    }
    state["participants"]["seller-0002"] = _make_participant(
        participant_id="seller-0002", role="investor", holdings=0, capital=5_000
    )
    state["market_actions"] = {
        "buyer-0001": _make_action(agent_id="buyer-0001", action_type="buy", confidence=1.0),
        "seller-0002": _make_action(agent_id="seller-0002", action_type="sell", confidence=1.0),
    }

    result = node(state)

    assert result["last_outcome"].market_actions_resolved == 0
    assert result["participants"]["buyer-0001"].holdings == 0


def test_deterministic_same_inputs_same_outputs() -> None:
    state = _base_state("deterministic")
    state["market_actions"] = {
        "buyer-0001": _make_action(agent_id="buyer-0001", action_type="buy", confidence=0.7),
        "seller-0001": _make_action(agent_id="seller-0001", action_type="sell", confidence=0.2),
    }

    first = make_round_resolver_node(InMemoryEventStore())(state)
    second = make_round_resolver_node(InMemoryEventStore())(state)

    assert first["world"] == second["world"]
    assert first["participants"] == second["participants"]
    assert first["last_outcome"] == second["last_outcome"]


def test_emits_round_resolved_event_with_payload_schema() -> None:
    run_id = "event-payload"
    store = InMemoryEventStore()
    node = make_round_resolver_node(store)
    state = _base_state(run_id)
    state["market_actions"] = {
        "buyer-0001": _make_action(agent_id="buyer-0001", action_type="buy", confidence=0.9),
    }

    result = node(state)
    event = store.get_events_by_type(run_id, "ROUND_RESOLVED")[0]

    assert event.event_id == result["event_refs"][0]
    payload = RoundResolvedPayload.model_validate(event.payload)
    assert payload.round_no == 3
    assert payload.transactions_count == result["last_outcome"].market_actions_resolved


def test_segment_sentiment_updates_from_net_pressure() -> None:
    store = InMemoryEventStore()
    node = make_round_resolver_node(store)
    state = _base_state("sentiment")
    state["world"] = {
        "11680": _make_segment(sentiment_index=0.4),
        "11650": state["world"]["11650"],
    }
    state["market_actions"] = {
        "buyer-0001": _make_action(agent_id="buyer-0001", action_type="buy", confidence=0.8),
        "seller-0001": _make_action(agent_id="seller-0001", action_type="sell", confidence=0.2),
    }

    result = node(state)

    assert result["world"]["11680"].sentiment_index == pytest.approx(0.43)


def test_participant_deltas_computed_correctly() -> None:
    run_id = "participant-deltas"
    store = InMemoryEventStore()
    node = make_round_resolver_node(store)
    state = _base_state(run_id)
    state["market_actions"] = {
        "buyer-0001": _make_action(agent_id="buyer-0001", action_type="buy", confidence=1.0),
        "seller-0001": _make_action(agent_id="seller-0001", action_type="sell", confidence=1.0),
    }

    node(state)
    payload = RoundResolvedPayload.model_validate(store.get_events_by_type(run_id, "ROUND_RESOLVED")[0].payload)

    buyer_delta = payload.participant_deltas["buyer-0001"]
    seller_delta = payload.participant_deltas["seller-0001"]
    assert buyer_delta.holdings_change == 1
    assert buyer_delta.capital_change < 0
    assert seller_delta.holdings_change == -1
    assert seller_delta.capital_change > 0


def test_missing_world_raises_value_error() -> None:
    store = InMemoryEventStore()
    node = make_round_resolver_node(store)
    state = _base_state("missing-world")
    del state["world"]

    with pytest.raises(ValueError, match="world is required"):
        node(state)


def test_missing_run_meta_raises_value_error() -> None:
    store = InMemoryEventStore()
    node = make_round_resolver_node(store)
    state = _base_state("missing-run-meta")
    del state["run_meta"]

    with pytest.raises(ValueError, match="run_meta is required"):
        node(state)


def test_zero_participants_noop_outcome_and_event() -> None:
    run_id = "zero-participants"
    store = InMemoryEventStore()
    node = make_round_resolver_node(store)
    state = _base_state(run_id)
    state["participants"] = {}
    state["market_actions"] = {
        "buyer-0001": _make_action(agent_id="buyer-0001", action_type="buy"),
    }

    result = node(state)
    event = store.get_events_by_type(run_id, "ROUND_RESOLVED")[0]

    assert result["last_outcome"].cleared_volume == {}
    assert result["last_outcome"].market_actions_resolved == 0
    assert RoundResolvedPayload.model_validate(event.payload).participant_deltas == {}


def test_hold_actions_affect_denominator_only() -> None:
    store = InMemoryEventStore()
    node = make_round_resolver_node(store)
    state = _base_state("hold-denominator")
    state["market_actions"] = {
        "buyer-0001": _make_action(agent_id="buyer-0001", action_type="buy", confidence=1.0),
        "seller-0001": _make_action(agent_id="seller-0001", action_type="hold", confidence=1.0),
    }

    result = node(state)

    assert result["last_outcome"].price_changes["11680"] == pytest.approx(0.025)


def test_price_trend_flat_with_small_change() -> None:
    store = InMemoryEventStore()
    node = make_round_resolver_node(store)
    state = _base_state("trend-flat")
    state["market_actions"] = {
        "buyer-0001": _make_action(agent_id="buyer-0001", action_type="buy", confidence=0.02),
    }

    result = node(state)

    assert result["world"]["11680"].price_trend == "flat"


def test_price_trend_up_with_threshold_breach() -> None:
    store = InMemoryEventStore()
    node = make_round_resolver_node(store)
    state = _base_state("trend-up")
    state["market_actions"] = {
        "buyer-0001": _make_action(agent_id="buyer-0001", action_type="buy", confidence=0.03),
    }

    result = node(state)

    assert result["world"]["11680"].price_trend == "up"


def test_price_trend_down_with_threshold_breach() -> None:
    store = InMemoryEventStore()
    node = make_round_resolver_node(store)
    state = _base_state("trend-down")
    state["market_actions"] = {
        "seller-0001": _make_action(agent_id="seller-0001", action_type="sell", confidence=0.03),
    }

    result = node(state)

    assert result["world"]["11680"].price_trend == "down"


def test_volume_update_is_damped_toward_matched_transactions() -> None:
    store = InMemoryEventStore()
    node = make_round_resolver_node(store)
    state = _base_state("volume-damped")
    state["market_actions"] = {
        "buyer-0001": _make_action(agent_id="buyer-0001", action_type="buy", confidence=1.0),
        "buyer-0002": _make_action(agent_id="buyer-0002", action_type="buy", confidence=1.0),
    }

    result = node(state)

    assert result["world"]["11680"].current_volume == 91


def test_invalid_action_type_is_ignored_with_warning() -> None:
    store = InMemoryEventStore()
    node = make_round_resolver_node(store)
    state = _base_state("invalid-action")
    state["market_actions"] = {
        "seller-0001": _make_action(agent_id="seller-0001", action_type="rent_out"),
    }

    result = node(state)

    assert result["last_outcome"].market_actions_resolved == 0
    assert any("unsupported action_type" in warning for warning in result["warnings"])


def test_unknown_segment_action_is_ignored_with_warning() -> None:
    store = InMemoryEventStore()
    node = make_round_resolver_node(store)
    state = _base_state("unknown-segment")
    state["market_actions"] = {
        "buyer-0001": _make_action(agent_id="buyer-0001", target_segment="99999"),
    }

    result = node(state)

    assert result["last_outcome"].price_changes == {}
    assert any("unknown gu_code" in warning for warning in result["warnings"])


def test_unknown_participant_action_is_ignored_with_warning() -> None:
    store = InMemoryEventStore()
    node = make_round_resolver_node(store)
    state = _base_state("unknown-participant")
    state["market_actions"] = {
        "ghost": _make_action(agent_id="ghost", action_type="buy"),
    }

    result = node(state)

    assert result["last_outcome"].market_actions_resolved == 0
    assert any("unknown participant_id=ghost" in warning for warning in result["warnings"])


def test_participant_matching_order_is_deterministic_by_id() -> None:
    store = InMemoryEventStore()
    node = make_round_resolver_node(store)
    state = _base_state("ordering")
    state["participants"]["buyer-0000"] = _make_participant(participant_id="buyer-0000", role="buyer", capital=10_000)
    state["participants"]["buyer-0009"] = _make_participant(participant_id="buyer-0009", role="buyer", capital=10_000)
    state["world"] = {
        "11680": _make_segment(current_volume=0),
        "11650": state["world"]["11650"],
    }
    state["market_actions"] = {
        "buyer-0009": _make_action(agent_id="buyer-0009", action_type="buy", confidence=1.0),
        "buyer-0000": _make_action(agent_id="buyer-0000", action_type="buy", confidence=1.0),
        "seller-0001": _make_action(agent_id="seller-0001", action_type="sell", confidence=1.0),
    }

    result = node(state)

    assert result["participants"]["buyer-0000"].holdings == 1
    assert result["participants"]["buyer-0009"].holdings == 0


def test_outcome_round_no_uses_state_round_no() -> None:
    store = InMemoryEventStore()
    node = make_round_resolver_node(store)
    state = _base_state("round-no")
    state["round_no"] = 9
    state["market_actions"] = {
        "buyer-0001": _make_action(action_type="buy"),
    }

    result = node(state)

    assert result["last_outcome"].round_no == 9


def test_event_round_no_matches_state_round_no() -> None:
    run_id = "event-round"
    store = InMemoryEventStore()
    node = make_round_resolver_node(store)
    state = _base_state(run_id)
    state["round_no"] = 8
    state["market_actions"] = {
        "buyer-0001": _make_action(action_type="buy"),
    }

    node(state)
    event = store.get_events_by_type(run_id, "ROUND_RESOLVED")[0]

    assert event.round_no == 8


def test_event_timestamp_is_timezone_aware() -> None:
    run_id = "event-timezone"
    store = InMemoryEventStore()
    node = make_round_resolver_node(store)
    state = _base_state(run_id)

    node(state)
    event = store.get_events_by_type(run_id, "ROUND_RESOLVED")[0]

    assert isinstance(event.timestamp, datetime)
    assert event.timestamp.tzinfo == timezone.utc


def test_returns_expected_result_keys() -> None:
    store = InMemoryEventStore()
    node = make_round_resolver_node(store)
    result = node(_base_state("result-keys"))

    assert set(result.keys()) == {"world", "participants", "last_outcome", "event_refs", "warnings"}


def test_summary_contains_round_and_transaction_count() -> None:
    run_id = "summary"
    store = InMemoryEventStore()
    node = make_round_resolver_node(store)
    state = _base_state(run_id)
    state["market_actions"] = {
        "buyer-0001": _make_action(action_type="buy"),
    }

    node(state)
    payload = RoundResolvedPayload.model_validate(store.get_events_by_type(run_id, "ROUND_RESOLVED")[0].payload)

    assert "Round 3" in payload.summary
    assert "transactions" in payload.summary
