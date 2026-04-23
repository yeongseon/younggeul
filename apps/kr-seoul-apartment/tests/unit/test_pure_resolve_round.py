"""Pure-resolver-math parity test.

Asserts that the extracted :func:`pure_resolve_round` helper produces the
same world / participants / outcome / payload as the LangGraph round
resolver node, for representative scenarios. This is the byte-identity
guarantee for Oracle's design ruling F for the shadow-runner work (no fork between LangGraph and
abdp shadow runner).
"""

from __future__ import annotations

# pyright: reportMissingImports=false

from datetime import date
from typing import Any

from younggeul_app_kr_seoul_apartment.simulation.event_store import InMemoryEventStore
from younggeul_app_kr_seoul_apartment.simulation.graph_state import SimulationGraphState, seed_graph_state
from younggeul_app_kr_seoul_apartment.simulation.nodes._resolver_math import pure_resolve_round
from younggeul_app_kr_seoul_apartment.simulation.nodes.round_resolver import make_round_resolver_node
from younggeul_core.state.simulation import ActionProposal, ParticipantState, ScenarioSpec, SegmentState


def _scenario() -> ScenarioSpec:
    return ScenarioSpec(
        scenario_name="parity",
        target_gus=["11680"],
        target_period_start=date(2026, 1, 1),
        target_period_end=date(2026, 6, 1),
        shocks=[],
    )


def _world() -> dict[str, SegmentState]:
    return {
        "11680": SegmentState(
            gu_code="11680",
            gu_name="강남구",
            current_median_price=1_000,
            current_volume=100,
            price_trend="flat",
            sentiment_index=0.5,
            supply_pressure=0.0,
        ),
    }


def _participants() -> dict[str, ParticipantState]:
    return {
        "buyer-0001": ParticipantState(
            participant_id="buyer-0001",
            role="buyer",
            capital=10_000,
            holdings=0,
            sentiment="bullish",
            risk_tolerance=0.6,
        ),
        "seller-0001": ParticipantState(
            participant_id="seller-0001",
            role="investor",
            capital=2_000,
            holdings=3,
            sentiment="bearish",
            risk_tolerance=0.5,
        ),
    }


def _actions() -> dict[str, ActionProposal]:
    return {
        "buyer-0001": ActionProposal(
            agent_id="buyer-0001",
            round_no=1,
            action_type="buy",
            target_segment="11680",
            confidence=0.9,
            reasoning_summary="bull",
        ),
        "seller-0001": ActionProposal(
            agent_id="seller-0001",
            round_no=1,
            action_type="sell",
            target_segment="11680",
            confidence=0.7,
            reasoning_summary="bear",
        ),
    }


def _state(
    world: dict[str, SegmentState], participants: dict[str, ParticipantState], actions: dict[str, Any], round_no: int
) -> SimulationGraphState:
    state = seed_graph_state("q", "rid", "rname", "stub")
    state["round_no"] = round_no
    state["scenario"] = _scenario()
    state["world"] = world
    state["participants"] = participants
    state["market_actions"] = actions
    state["last_outcome"] = None
    return state


def test_pure_helper_matches_node_with_buy_sell_actions() -> None:
    world = _world()
    participants = _participants()
    actions = _actions()

    pure = pure_resolve_round(
        world=world,
        participants=participants,
        market_actions=actions,
        round_no=1,
    )

    store = InMemoryEventStore()
    node_state = _state(world, participants, actions, round_no=1)
    node_out = make_round_resolver_node(store)(node_state)

    assert pure.new_world == node_out["world"]
    assert pure.new_participants == node_out["participants"]
    assert pure.outcome == node_out["last_outcome"]
    assert pure.warnings == node_out["warnings"]
    events = store.get_events("rid")
    assert len(events) == 1
    assert events[0].payload == pure.payload.model_dump()


def test_pure_helper_returns_empty_outcome_for_no_participants() -> None:
    world = _world()
    pure = pure_resolve_round(
        world=world,
        participants={},
        market_actions={},
        round_no=2,
    )
    assert pure.outcome.cleared_volume == {}
    assert pure.outcome.market_actions_resolved == 0
    assert pure.payload.transactions_count == 0
    assert pure.warnings == []
    assert pure.new_world == world


def test_pure_helper_warns_on_unknown_participant_action() -> None:
    world = _world()
    participants = _participants()
    actions = {
        "ghost-0001": ActionProposal(
            agent_id="ghost-0001",
            round_no=1,
            action_type="buy",
            target_segment="11680",
            confidence=0.5,
            reasoning_summary="ghost",
        )
    }
    pure = pure_resolve_round(
        world=world,
        participants=participants,
        market_actions=actions,
        round_no=1,
    )
    assert any("ghost-0001" in w for w in pure.warnings)
    assert pure.outcome.market_actions_resolved == 0


def test_pure_helper_does_not_mutate_inputs() -> None:
    world = _world()
    participants = _participants()
    actions = _actions()
    world_snapshot = dict(world)
    part_snapshot = dict(participants)
    pure_resolve_round(
        world=world,
        participants=participants,
        market_actions=actions,
        round_no=1,
    )
    assert world == world_snapshot
    assert participants == part_snapshot
