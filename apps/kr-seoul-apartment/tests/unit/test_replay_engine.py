from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from importlib import import_module
from typing import Any

import pytest

event_store_module = import_module("younggeul_app_kr_seoul_apartment.simulation.event_store")
events_module = import_module("younggeul_app_kr_seoul_apartment.simulation.events")
replay_module = import_module("younggeul_app_kr_seoul_apartment.simulation.replay")
intake_module = import_module("younggeul_app_kr_seoul_apartment.simulation.schemas.intake")
roster_module = import_module("younggeul_app_kr_seoul_apartment.simulation.schemas.participant_roster")
simulation_state_module = import_module("younggeul_core.state.simulation")

InMemoryEventStore = event_store_module.InMemoryEventStore
SimulationEvent = events_module.SimulationEvent
HANDLERS = replay_module.HANDLERS
ReplayContext = replay_module.ReplayContext
ReplayEngine = replay_module.ReplayEngine
ReplayError = replay_module.ReplayError
IntakePlan = intake_module.IntakePlan
ParticipantRosterSpec = roster_module.ParticipantRosterSpec
RoleBucketSpec = roster_module.RoleBucketSpec
ScenarioSpec = simulation_state_module.ScenarioSpec
RoundOutcome = simulation_state_module.RoundOutcome


def _event(
    *,
    event_id: str,
    run_id: str = "run-001",
    event_type: str,
    payload: dict[str, Any],
    offset_seconds: int = 0,
) -> SimulationEvent:
    return SimulationEvent(
        event_id=event_id,
        run_id=run_id,
        round_no=0,
        event_type=event_type,
        timestamp=datetime(2026, 3, 29, 12, 0, 0, tzinfo=timezone.utc) + timedelta(seconds=offset_seconds),
        payload=payload,
    )


def _intake_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = IntakePlan(
        user_query="강남구 아파트 전망을 분석해줘",
        objective="금리 충격에 대한 가격 반응을 파악한다.",
        analysis_mode="stress",
        geography_hint="강남구",
        segment_hint="아파트",
        horizon_months=12,
        requested_shocks=["금리인상"],
        participant_focus=["실수요자", "투자자"],
        constraints=[],
        assumptions=[],
        ambiguities=[],
    ).model_dump()
    payload.update(overrides)
    return payload


def _scenario_payload(**overrides: Any) -> dict[str, Any]:
    scenario = ScenarioSpec(
        scenario_name="Stress Alpha",
        target_gus=["11680", "11650"],
        target_period_start=date(2026, 1, 1),
        target_period_end=date(2026, 6, 1),
        shocks=[],
    )
    roster = ParticipantRosterSpec(
        seed="seed-01",
        buckets=[
            RoleBucketSpec(
                role="buyer",
                count=4,
                capital_min_multiplier=0.8,
                capital_max_multiplier=1.2,
                holdings_min=0,
                holdings_max=2,
                risk_min=0.2,
                risk_max=0.8,
                sentiment_bias="neutral",
            )
        ],
    )
    payload: dict[str, Any] = {
        "scenario": scenario.model_dump(),
        "participant_roster": roster.model_dump(),
        "max_rounds": 4,
        "warnings": ["Scenario warning"],
    }
    payload.update(overrides)
    return payload


def _world_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "world_summary": {
            "11680": {"median_price": 1_900_000, "volume": 130},
            "11650": {"median_price": 1_700_000, "volume": 90},
        },
        "participant_count": 12,
        "anchor_period": "2025-12",
        "warnings": ["World warning"],
    }
    payload.update(overrides)
    return payload


def _decisions_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "round_no": 2,
        "action_summary": {
            "buyer-0001": {"action_type": "buy", "target": "11680"},
            "investor-0001": {"action_type": "hold", "target": "11650"},
        },
        "total_actions": 2,
    }
    payload.update(overrides)
    return payload


def _round_resolved_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "round_no": 2,
        "transactions_count": 3,
        "summary": "Round 2 resolved with 3 transactions",
        "warnings": ["resolver warning"],
    }
    payload.update(overrides)
    return payload


def _simulation_completed_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "total_rounds": 4,
        "world_summary": {"11680": {"median_price": 2_100_000, "volume": 110}},
        "participant_summary": {"buyer": {"count": 1, "total_capital": 100, "total_holdings": 0}},
        "total_warnings": 0,
    }
    payload.update(overrides)
    return payload


class TestReplayEngine:
    def test_replay_all_supported_events_returns_full_result(self) -> None:
        store = InMemoryEventStore()
        store.append(_event(event_id="evt-1", event_type="INTAKE_PLANNED", payload=_intake_payload(), offset_seconds=0))
        store.append(
            _event(event_id="evt-2", event_type="SCENARIO_BUILT", payload=_scenario_payload(), offset_seconds=1)
        )
        store.append(
            _event(event_id="evt-3", event_type="WORLD_INITIALIZED", payload=_world_payload(), offset_seconds=2)
        )

        result = ReplayEngine(store).replay("run-001")

        assert result.completeness == "full"
        assert result.event_count == 3
        assert result.state["user_query"] == "강남구 아파트 전망을 분석해줘"
        assert result.state["max_rounds"] == 4
        assert result.world_summary is not None
        assert result.participant_count == 12
        assert result.anchor_period == "2025-12"

    def test_decisions_made_handler_sets_round_no_and_market_actions_summary(self) -> None:
        store = InMemoryEventStore()
        store.append(
            _event(event_id="evt-1", event_type="DECISIONS_MADE", payload=_decisions_payload(), offset_seconds=0)
        )

        result = ReplayEngine(store).replay("run-001")

        assert result.state["round_no"] == 2
        assert result.state["market_actions"] == _decisions_payload()["action_summary"]

    def test_round_resolved_handler_sets_round_no_and_last_outcome(self) -> None:
        store = InMemoryEventStore()
        store.append(
            _event(event_id="evt-1", event_type="ROUND_RESOLVED", payload=_round_resolved_payload(), offset_seconds=0)
        )

        result = ReplayEngine(store).replay("run-001")

        assert result.state["round_no"] == 2
        assert isinstance(result.state["last_outcome"], RoundOutcome)
        assert result.state["last_outcome"].round_no == 2
        assert result.state["last_outcome"].market_actions_resolved == 3
        assert result.state["warnings"] == ["resolver warning"]

    def test_simulation_completed_handler_sets_final_round_no(self) -> None:
        store = InMemoryEventStore()
        store.append(
            _event(
                event_id="evt-1",
                event_type="SIMULATION_COMPLETED",
                payload=_simulation_completed_payload(total_rounds=7),
            )
        )

        result = ReplayEngine(store).replay("run-001")

        assert result.state["round_no"] == 7

    def test_replay_m6_event_stream_including_round_events_and_completion(self) -> None:
        store = InMemoryEventStore()
        store.append(_event(event_id="evt-1", event_type="INTAKE_PLANNED", payload=_intake_payload(), offset_seconds=0))
        store.append(
            _event(event_id="evt-2", event_type="SCENARIO_BUILT", payload=_scenario_payload(), offset_seconds=1)
        )
        store.append(
            _event(event_id="evt-3", event_type="WORLD_INITIALIZED", payload=_world_payload(), offset_seconds=2)
        )
        store.append(
            _event(event_id="evt-4", event_type="DECISIONS_MADE", payload=_decisions_payload(), offset_seconds=3)
        )
        store.append(
            _event(event_id="evt-5", event_type="ROUND_RESOLVED", payload=_round_resolved_payload(), offset_seconds=4)
        )
        store.append(
            _event(
                event_id="evt-6",
                event_type="SIMULATION_COMPLETED",
                payload=_simulation_completed_payload(total_rounds=2),
                offset_seconds=5,
            )
        )

        result = ReplayEngine(store).replay("run-001", strict=True)

        assert result.completeness == "full"
        assert result.event_count == 6
        assert result.state["round_no"] == 2
        assert result.state["market_actions"] == _decisions_payload()["action_summary"]
        assert isinstance(result.state["last_outcome"], RoundOutcome)

    def test_replay_intake_only_is_partial(self) -> None:
        store = InMemoryEventStore()
        store.append(_event(event_id="evt-1", event_type="INTAKE_PLANNED", payload=_intake_payload()))

        result = ReplayEngine(store).replay("run-001")

        assert result.completeness == "partial"
        assert "intake_plan" in result.state
        assert result.state["user_query"] == _intake_payload()["user_query"]
        assert "scenario" not in result.state

    def test_unknown_event_type_strict_mode_raises(self) -> None:
        store = InMemoryEventStore()
        store.append(_event(event_id="evt-1", event_type="UNKNOWN", payload={}))

        with pytest.raises(ReplayError, match="Unknown event type"):
            ReplayEngine(store).replay("run-001", strict=True)

    def test_unknown_event_type_best_effort_skips_with_warning(self) -> None:
        store = InMemoryEventStore()
        store.append(_event(event_id="evt-1", event_type="INTAKE_PLANNED", payload=_intake_payload(), offset_seconds=0))
        store.append(_event(event_id="evt-2", event_type="UNKNOWN", payload={}, offset_seconds=1))

        result = ReplayEngine(store).replay("run-001", strict=False)

        assert result.event_count == 2
        assert any("Skipped unknown event type" in warning for warning in result.warnings)
        assert "intake_plan" in result.state

    def test_empty_event_store_returns_partial_with_warning(self) -> None:
        store = InMemoryEventStore()

        result = ReplayEngine(store).replay("missing-run")

        assert result.completeness == "partial"
        assert result.event_count == 0
        assert result.state == {}
        assert len(result.warnings) == 1
        assert "No events found" in result.warnings[0]

    def test_world_initialized_does_not_set_world_or_participants_in_state(self) -> None:
        store = InMemoryEventStore()
        store.append(_event(event_id="evt-1", event_type="WORLD_INITIALIZED", payload=_world_payload()))

        result = ReplayEngine(store).replay("run-001")

        assert "world" not in result.state
        assert "participants" not in result.state

    def test_world_initialized_extracts_summary_metadata(self) -> None:
        store = InMemoryEventStore()
        store.append(_event(event_id="evt-1", event_type="WORLD_INITIALIZED", payload=_world_payload()))

        result = ReplayEngine(store).replay("run-001")

        assert result.world_summary == _world_payload()["world_summary"]
        assert result.participant_count == 12
        assert result.anchor_period == "2025-12"

    def test_replay_uses_timestamp_ordering(self) -> None:
        store = InMemoryEventStore()
        store.append(
            _event(event_id="evt-2", event_type="SCENARIO_BUILT", payload=_scenario_payload(), offset_seconds=10)
        )
        store.append(_event(event_id="evt-1", event_type="INTAKE_PLANNED", payload=_intake_payload(), offset_seconds=1))

        result = ReplayEngine(store).replay("run-001")

        assert result.state["user_query"] == _intake_payload()["user_query"]
        assert result.state["scenario"].scenario_name == "Stress Alpha"

    def test_multiple_runs_only_replays_target_run(self) -> None:
        store = InMemoryEventStore()
        store.append(_event(event_id="evt-a", run_id="run-a", event_type="INTAKE_PLANNED", payload=_intake_payload()))
        store.append(_event(event_id="evt-b", run_id="run-b", event_type="INTAKE_PLANNED", payload=_intake_payload()))

        result = ReplayEngine(store).replay("run-b")

        assert result.event_count == 1
        assert result.state["user_query"] == _intake_payload()["user_query"]

    def test_scenario_warnings_are_appended_to_state(self) -> None:
        store = InMemoryEventStore()
        store.append(
            _event(event_id="evt-1", event_type="SCENARIO_BUILT", payload=_scenario_payload(warnings=["w1", "w2"]))
        )

        result = ReplayEngine(store).replay("run-001")

        assert result.state["warnings"] == ["w1", "w2"]

    def test_world_warnings_are_appended_to_state(self) -> None:
        store = InMemoryEventStore()
        store.append(
            _event(event_id="evt-1", event_type="WORLD_INITIALIZED", payload=_world_payload(warnings=["world-warn"]))
        )

        result = ReplayEngine(store).replay("run-001")

        assert result.state["warnings"] == ["world-warn"]

    def test_result_warnings_include_state_and_replay_warnings(self) -> None:
        store = InMemoryEventStore()
        store.append(
            _event(event_id="evt-1", event_type="SCENARIO_BUILT", payload=_scenario_payload(warnings=["state-warn"]))
        )
        store.append(_event(event_id="evt-2", event_type="UNKNOWN", payload={}, offset_seconds=1))

        result = ReplayEngine(store).replay("run-001", strict=False)

        assert result.warnings[0] == "state-warn"
        assert any("Skipped unknown event type" in warning for warning in result.warnings)

    def test_invalid_intake_payload_raises_replay_error(self) -> None:
        store = InMemoryEventStore()
        store.append(
            _event(
                event_id="evt-1",
                event_type="INTAKE_PLANNED",
                payload={"user_query": "q", "objective": "o", "analysis_mode": "baseline"},
            )
        )

        with pytest.raises(ReplayError, match="Invalid INTAKE_PLANNED payload"):
            ReplayEngine(store).replay("run-001")

    def test_invalid_scenario_payload_raises_replay_error(self) -> None:
        store = InMemoryEventStore()
        bad_scenario = {"scenario_name": "bad"}
        store.append(
            _event(
                event_id="evt-1",
                event_type="SCENARIO_BUILT",
                payload=_scenario_payload(scenario=bad_scenario),
            )
        )

        with pytest.raises(ReplayError, match="Invalid SCENARIO_BUILT scenario payload"):
            ReplayEngine(store).replay("run-001")

    def test_missing_participant_roster_raises_replay_error(self) -> None:
        store = InMemoryEventStore()
        payload = _scenario_payload()
        del payload["participant_roster"]
        store.append(_event(event_id="evt-1", event_type="SCENARIO_BUILT", payload=payload))

        with pytest.raises(ReplayError, match="missing participant_roster"):
            ReplayEngine(store).replay("run-001")

    def test_missing_max_rounds_raises_replay_error(self) -> None:
        store = InMemoryEventStore()
        payload = _scenario_payload()
        del payload["max_rounds"]
        store.append(_event(event_id="evt-1", event_type="SCENARIO_BUILT", payload=payload))

        with pytest.raises(ReplayError, match="missing max_rounds"):
            ReplayEngine(store).replay("run-001")

    def test_non_list_warnings_in_payload_are_ignored(self) -> None:
        store = InMemoryEventStore()
        store.append(
            _event(event_id="evt-1", event_type="SCENARIO_BUILT", payload=_scenario_payload(warnings="not-a-list"))
        )

        result = ReplayEngine(store).replay("run-001")

        assert "warnings" not in result.state

    def test_invalid_world_summary_shape_is_filtered(self) -> None:
        store = InMemoryEventStore()
        store.append(
            _event(
                event_id="evt-1",
                event_type="WORLD_INITIALIZED",
                payload=_world_payload(world_summary={"11680": {"median_price": 1_0}, "bad": 123}),
            )
        )

        result = ReplayEngine(store).replay("run-001")

        assert result.world_summary == {"11680": {"median_price": 10}}

    def test_best_effort_with_unknown_event_can_still_be_partial(self) -> None:
        store = InMemoryEventStore()
        store.append(_event(event_id="evt-1", event_type="INTAKE_PLANNED", payload=_intake_payload()))
        store.append(_event(event_id="evt-2", event_type="UNKNOWN", payload={}, offset_seconds=1))

        result = ReplayEngine(store).replay("run-001", strict=False)

        assert result.completeness == "partial"

    def test_round_trip_event_backed_fields_match(self) -> None:
        intake_payload = _intake_payload()
        scenario_payload = _scenario_payload()
        world_payload = _world_payload()

        store = InMemoryEventStore()
        store.append(_event(event_id="evt-1", event_type="INTAKE_PLANNED", payload=intake_payload, offset_seconds=0))
        store.append(_event(event_id="evt-2", event_type="SCENARIO_BUILT", payload=scenario_payload, offset_seconds=1))
        store.append(_event(event_id="evt-3", event_type="WORLD_INITIALIZED", payload=world_payload, offset_seconds=2))

        result = ReplayEngine(store).replay("run-001")

        assert result.state["intake_plan"] == intake_payload
        assert result.state["participant_roster"] == scenario_payload["participant_roster"]
        assert result.state["max_rounds"] == scenario_payload["max_rounds"]
        assert result.world_summary == world_payload["world_summary"]
        assert result.participant_count == world_payload["participant_count"]
        assert result.anchor_period == world_payload["anchor_period"]

    def test_latest_world_initialized_event_wins_for_metadata(self) -> None:
        store = InMemoryEventStore()
        store.append(
            _event(event_id="evt-1", event_type="WORLD_INITIALIZED", payload=_world_payload(anchor_period="2025-11"))
        )
        store.append(
            _event(
                event_id="evt-2",
                event_type="WORLD_INITIALIZED",
                payload=_world_payload(anchor_period="2025-12", participant_count=33),
                offset_seconds=1,
            )
        )

        result = ReplayEngine(store).replay("run-001")

        assert result.anchor_period == "2025-12"
        assert result.participant_count == 33

    def test_handlers_registry_contains_required_event_types(self) -> None:
        assert set(HANDLERS.keys()) == {
            "INTAKE_PLANNED",
            "SCENARIO_BUILT",
            "WORLD_INITIALIZED",
            "DECISIONS_MADE",
            "ROUND_RESOLVED",
            "SIMULATION_COMPLETED",
        }

    def test_replay_context_defaults_to_strict(self) -> None:
        context = ReplayContext()

        assert context.strict is True

    def test_replay_context_can_disable_strict(self) -> None:
        context = ReplayContext(strict=False)

        assert context.strict is False
