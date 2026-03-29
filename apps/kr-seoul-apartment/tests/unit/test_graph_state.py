from __future__ import annotations

import operator
from datetime import date, datetime, timedelta, timezone
from typing import Any, Annotated, cast, get_args, get_origin, get_type_hints

import pytest

from younggeul_app_kr_seoul_apartment.simulation.graph_state import (
    SimulationGraphState,
    seed_graph_state,
    to_simulation_state,
    validate_initialized_state,
)
from younggeul_core.state.simulation import (
    ActionProposal,
    ParticipantState,
    ReportClaim,
    RoundOutcome,
    RunMeta,
    ScenarioSpec,
    SegmentState,
    SimulationState,
    SnapshotRef,
)


def _make_run_meta(**overrides: Any) -> RunMeta:
    payload: dict[str, Any] = {
        "run_id": "run-test-001",
        "run_name": "graph-state-test",
        "created_at": datetime(2026, 3, 29, 12, 0, 0, tzinfo=timezone.utc),
        "model_id": "gpt-test-v1",
        "config_hash": "cfg-hash-001",
    }
    payload.update(overrides)
    return RunMeta(**payload)


def _make_snapshot_ref(**overrides: Any) -> SnapshotRef:
    payload: dict[str, Any] = {
        "dataset_snapshot_id": "a" * 64,
        "created_at": datetime(2026, 3, 29, 12, 0, 0, tzinfo=timezone.utc),
        "table_count": 3,
    }
    payload.update(overrides)
    return SnapshotRef(**payload)


def _make_scenario_spec(**overrides: Any) -> ScenarioSpec:
    payload: dict[str, Any] = {
        "scenario_name": "Base Case",
        "target_gus": ["11680", "11710"],
        "target_period_start": date(2026, 1, 1),
        "target_period_end": date(2026, 12, 31),
        "shocks": [],
    }
    payload.update(overrides)
    return ScenarioSpec(**payload)


def _make_segment_state(**overrides: Any) -> SegmentState:
    payload: dict[str, Any] = {
        "gu_code": "11680",
        "gu_name": "강남구",
        "current_median_price": 2_000_000,
        "current_volume": 120,
        "price_trend": "up",
        "sentiment_index": 0.65,
        "supply_pressure": -0.2,
    }
    payload.update(overrides)
    return SegmentState(**payload)


def _make_participant_state(**overrides: Any) -> ParticipantState:
    payload: dict[str, Any] = {
        "participant_id": "p-001",
        "role": "buyer",
        "capital": 900_000,
        "holdings": 1,
        "sentiment": "bullish",
        "risk_tolerance": 0.7,
    }
    payload.update(overrides)
    return ParticipantState(**payload)


def _make_action_proposal(**overrides: Any) -> ActionProposal:
    payload: dict[str, Any] = {
        "agent_id": "agent-001",
        "round_no": 1,
        "action_type": "buy",
        "target_segment": "11680",
        "confidence": 0.8,
        "reasoning_summary": "momentum suggests upside",
        "proposed_value": {"units": 1},
    }
    payload.update(overrides)
    return ActionProposal(**payload)


def _make_round_outcome(**overrides: Any) -> RoundOutcome:
    payload: dict[str, Any] = {
        "round_no": 1,
        "cleared_volume": {"11680": 15},
        "price_changes": {"11680": 0.01},
        "governance_applied": ["rate_hold"],
        "market_actions_resolved": 2,
    }
    payload.update(overrides)
    return RoundOutcome(**payload)


def _make_report_claim(**overrides: Any) -> ReportClaim:
    payload: dict[str, Any] = {
        "claim_id": "claim-001",
        "claim_json": {"headline": "Price up"},
        "evidence_ids": ["ev-001"],
        "gate_status": "passed",
        "repair_count": 0,
    }
    payload.update(overrides)
    return ReportClaim(**payload)


def _make_full_graph_state(**overrides: Any) -> SimulationGraphState:
    payload: SimulationGraphState = {
        "user_query": "서울 아파트 시뮬레이션",
        "intake_plan": {"goal": "stress test"},
        "run_meta": _make_run_meta(),
        "snapshot": _make_snapshot_ref(),
        "scenario": _make_scenario_spec(),
        "round_no": 1,
        "max_rounds": 6,
        "world": {
            "11680": _make_segment_state(),
        },
        "participants": {
            "p-001": _make_participant_state(),
        },
        "governance_actions": {
            "gov-001": _make_action_proposal(action_type="regulate"),
        },
        "market_actions": {
            "mkt-001": _make_action_proposal(action_type="buy"),
        },
        "last_outcome": _make_round_outcome(),
        "event_refs": ["event-001"],
        "evidence_refs": ["ev-001"],
        "report_claims": [_make_report_claim()],
        "warnings": ["low liquidity"],
    }
    payload.update(overrides)
    return payload


class TestSimulationGraphState:
    def test_type_is_typed_dict_like(self) -> None:
        assert isinstance(SimulationGraphState.__annotations__, dict)
        assert SimulationGraphState.__total__ is False

    def test_can_be_instantiated_with_minimal_fields(self) -> None:
        state: SimulationGraphState = {"user_query": "test"}

        assert state["user_query"] == "test"

    def test_can_be_instantiated_with_all_fields(self) -> None:
        state = _make_full_graph_state()

        assert state["scenario"].scenario_name == "Base Case"
        assert state["world"]["11680"].gu_name == "강남구"

    def test_event_refs_has_append_reducer_annotation(self) -> None:
        hints = get_type_hints(SimulationGraphState, include_extras=True)
        annotation = hints["event_refs"]

        assert get_origin(annotation) is Annotated
        assert get_args(annotation)[1] is operator.add

    def test_evidence_refs_has_append_reducer_annotation(self) -> None:
        hints = get_type_hints(SimulationGraphState, include_extras=True)
        annotation = hints["evidence_refs"]

        assert get_origin(annotation) is Annotated
        assert get_args(annotation)[1] is operator.add

    def test_report_claims_has_append_reducer_annotation(self) -> None:
        hints = get_type_hints(SimulationGraphState, include_extras=True)
        annotation = hints["report_claims"]

        assert get_origin(annotation) is Annotated
        assert get_args(annotation)[1] is operator.add

    def test_warnings_has_append_reducer_annotation(self) -> None:
        hints = get_type_hints(SimulationGraphState, include_extras=True)
        annotation = hints["warnings"]

        assert get_origin(annotation) is Annotated
        assert get_args(annotation)[1] is operator.add


class TestSeedGraphState:
    def test_returns_dict_with_user_query_set(self) -> None:
        state = seed_graph_state("simulate seoul", "run-1", "demo", "model-x")

        assert state["user_query"] == "simulate seoul"

    def test_returns_dict_with_run_meta_populated(self) -> None:
        state = seed_graph_state("query", "run-1", "demo", "model-x")

        assert isinstance(state["run_meta"], RunMeta)

    def test_returns_empty_accumulator_lists(self) -> None:
        state = seed_graph_state("query", "run-1", "demo", "model-x")

        assert state["event_refs"] == []
        assert state["evidence_refs"] == []
        assert state["report_claims"] == []
        assert state["warnings"] == []

    def test_does_not_include_uninitialized_core_fields(self) -> None:
        state = seed_graph_state("query", "run-1", "demo", "model-x")

        assert "scenario" not in state
        assert "world" not in state
        assert "participants" not in state

    def test_run_meta_has_expected_ids(self) -> None:
        state = seed_graph_state("query", "run-22", "my-run", "model-y")
        run_meta = state["run_meta"]

        assert run_meta.run_id == "run-22"
        assert run_meta.run_name == "my-run"
        assert run_meta.model_id == "model-y"

    def test_created_at_is_recent_utc(self) -> None:
        before = datetime.now(timezone.utc) - timedelta(seconds=1)

        state = seed_graph_state("query", "run-1", "demo", "model-x")

        after = datetime.now(timezone.utc) + timedelta(seconds=1)
        created_at = state["run_meta"].created_at
        assert before <= created_at <= after
        assert created_at.tzinfo is not None

    def test_run_meta_config_hash_defaults_to_none(self) -> None:
        state = seed_graph_state("query", "run-1", "demo", "model-x")

        assert state["run_meta"].config_hash is None


class TestToSimulationState:
    def test_converts_fully_populated_graph_state(self) -> None:
        graph_state = _make_full_graph_state()

        state = to_simulation_state(graph_state)

        assert isinstance(state, dict)
        assert state["snapshot"].dataset_snapshot_id == "a" * 64

    def test_preserves_all_values_through_conversion(self) -> None:
        graph_state = _make_full_graph_state()

        state = to_simulation_state(graph_state)

        assert state["run_meta"] == graph_state["run_meta"]
        assert state["scenario"] == graph_state["scenario"]
        assert state["world"] == graph_state["world"]
        assert state["participants"] == graph_state["participants"]
        assert state["governance_actions"] == graph_state["governance_actions"]
        assert state["market_actions"] == graph_state["market_actions"]
        assert state["last_outcome"] == graph_state["last_outcome"]
        assert state["event_refs"] == graph_state["event_refs"]
        assert state["evidence_refs"] == graph_state["evidence_refs"]
        assert state["report_claims"] == graph_state["report_claims"]
        assert state["warnings"] == graph_state["warnings"]

    def test_raises_value_error_when_required_field_missing(self) -> None:
        graph_state = _make_full_graph_state()
        graph_state.pop("scenario")

        with pytest.raises(ValueError):
            to_simulation_state(graph_state)

    def test_raises_value_error_for_seed_only_state(self) -> None:
        graph_state = seed_graph_state("query", "run-1", "demo", "model-x")

        with pytest.raises(ValueError):
            to_simulation_state(graph_state)

    def test_round_trip_seed_then_populate_then_convert(self) -> None:
        graph_state = seed_graph_state("query", "run-1", "demo", "model-x")
        graph_state.update(
            {
                "snapshot": _make_snapshot_ref(),
                "scenario": _make_scenario_spec(),
                "round_no": 0,
                "max_rounds": 5,
                "world": {"11680": _make_segment_state()},
                "participants": {"p-001": _make_participant_state()},
                "governance_actions": {},
                "market_actions": {},
                "last_outcome": None,
            }
        )

        state = to_simulation_state(graph_state)

        assert state["round_no"] == 0
        assert state["max_rounds"] == 5

    def test_conversion_result_matches_simulation_state_shape(self) -> None:
        graph_state = _make_full_graph_state()

        state = to_simulation_state(graph_state)

        simulation_keys = set(SimulationState.__annotations__)
        assert set(state.keys()) == simulation_keys

    def test_conversion_ignores_pre_initialization_only_fields(self) -> None:
        graph_state = _make_full_graph_state(
            user_query="custom query",
            intake_plan={"steps": ["a", "b"]},
        )

        state = to_simulation_state(graph_state)

        assert "user_query" not in state
        assert "intake_plan" not in state

    def test_invalid_required_field_type_raises_value_error(self) -> None:
        bad_state = cast(SimulationGraphState, {**_make_full_graph_state(), "round_no": "bad"})

        with pytest.raises(ValueError):
            to_simulation_state(bad_state)


class TestValidateInitializedState:
    def test_returns_false_for_seed_only_state(self) -> None:
        state = seed_graph_state("query", "run-1", "demo", "model-x")

        assert validate_initialized_state(state) is False

    def test_returns_true_for_fully_populated_state(self) -> None:
        state = _make_full_graph_state()

        assert validate_initialized_state(state) is True

    def test_returns_false_when_scenario_missing(self) -> None:
        state = _make_full_graph_state()
        state.pop("scenario")

        assert validate_initialized_state(state) is False

    def test_returns_false_when_world_missing(self) -> None:
        state = _make_full_graph_state()
        state.pop("world")

        assert validate_initialized_state(state) is False

    def test_returns_false_when_participants_missing(self) -> None:
        state = _make_full_graph_state()
        state.pop("participants")

        assert validate_initialized_state(state) is False

    def test_returns_false_when_required_value_is_none(self) -> None:
        state = cast(SimulationGraphState, {**_make_full_graph_state(), "scenario": None})

        assert validate_initialized_state(state) is False

    def test_ignores_non_required_field_presence(self) -> None:
        state = _make_full_graph_state()
        state.pop("user_query")
        state.pop("intake_plan")

        assert validate_initialized_state(state) is True
