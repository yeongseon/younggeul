from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any, Callable, Literal

from pydantic import ValidationError

from ..events import EventStore, SimulationEvent
from ..graph_state import SimulationGraphState
from ..schemas.intake import IntakePlan


@dataclass(frozen=True)
class ReplayResult:
    state: SimulationGraphState
    completeness: Literal["partial", "full"]
    event_count: int
    warnings: list[str]
    world_summary: dict[str, dict[str, int]] | None
    participant_count: int | None
    anchor_period: str | None


@dataclass(frozen=True)
class ReplayContext:
    strict: bool = True


class ReplayError(Exception):
    pass


EventHandler = Callable[[SimulationGraphState, SimulationEvent, ReplayContext], SimulationGraphState]


def _copy_state(state: SimulationGraphState) -> SimulationGraphState:
    return {**state}


def _state_warnings(state: SimulationGraphState) -> list[str]:
    raw = state.get("warnings")
    if not isinstance(raw, list):
        return []
    return [warning for warning in raw if isinstance(warning, str)]


def _append_warnings(state: SimulationGraphState, warnings: list[str]) -> SimulationGraphState:
    if not warnings:
        return state

    next_state = _copy_state(state)
    existing = _state_warnings(next_state)
    next_state["warnings"] = existing + warnings
    return next_state


def _warning_list(payload: dict[str, Any]) -> list[str]:
    raw = payload.get("warnings", [])
    if not isinstance(raw, list):
        return []
    return [warning for warning in raw if isinstance(warning, str)]


def _handle_intake_planned(
    state: SimulationGraphState,
    event: SimulationEvent,
    context: ReplayContext,
) -> SimulationGraphState:
    _ = context
    try:
        intake_plan = IntakePlan.model_validate(event.payload)
    except ValidationError as exc:
        raise ReplayError(f"Invalid INTAKE_PLANNED payload for event_id={event.event_id}") from exc

    next_state = _copy_state(state)
    payload = intake_plan.model_dump()
    next_state["intake_plan"] = payload
    user_query = payload.get("user_query")
    if isinstance(user_query, str):
        next_state["user_query"] = user_query
    return next_state


def _handle_scenario_built(
    state: SimulationGraphState,
    event: SimulationEvent,
    context: ReplayContext,
) -> SimulationGraphState:
    _ = context

    raw_scenario = event.payload.get("scenario")
    if not isinstance(raw_scenario, dict):
        raise ReplayError(f"Invalid SCENARIO_BUILT payload for event_id={event.event_id}: missing scenario")

    scenario_spec_model = import_module("younggeul_core.state.simulation").ScenarioSpec
    try:
        scenario = scenario_spec_model.model_validate(raw_scenario)
    except ValidationError as exc:
        raise ReplayError(f"Invalid SCENARIO_BUILT scenario payload for event_id={event.event_id}") from exc

    next_state = _copy_state(state)
    next_state["scenario"] = scenario

    participant_roster = event.payload.get("participant_roster")
    if not isinstance(participant_roster, dict):
        raise ReplayError(f"Invalid SCENARIO_BUILT payload for event_id={event.event_id}: missing participant_roster")
    next_state["participant_roster"] = participant_roster

    max_rounds = event.payload.get("max_rounds")
    if not isinstance(max_rounds, int):
        raise ReplayError(f"Invalid SCENARIO_BUILT payload for event_id={event.event_id}: missing max_rounds")
    next_state["max_rounds"] = max_rounds

    return _append_warnings(next_state, _warning_list(event.payload))


def _handle_world_initialized(
    state: SimulationGraphState,
    event: SimulationEvent,
    context: ReplayContext,
) -> SimulationGraphState:
    _ = context
    return _append_warnings(state, _warning_list(event.payload))


HANDLERS: dict[str, EventHandler] = {
    "INTAKE_PLANNED": _handle_intake_planned,
    "SCENARIO_BUILT": _handle_scenario_built,
    "WORLD_INITIALIZED": _handle_world_initialized,
}


class ReplayEngine:
    def __init__(self, event_store: EventStore) -> None:
        self._event_store = event_store

    def replay(self, run_id: str, *, strict: bool = True) -> ReplayResult:
        context = ReplayContext(strict=strict)
        events = self._event_store.get_events(run_id)

        state: SimulationGraphState = {}
        replay_warnings: list[str] = []

        if not events:
            replay_warnings.append(f"No events found for run_id={run_id}.")
            return ReplayResult(
                state=state,
                completeness="partial",
                event_count=0,
                warnings=replay_warnings,
                world_summary=None,
                participant_count=None,
                anchor_period=None,
            )

        world_summary: dict[str, dict[str, int]] | None = None
        participant_count: int | None = None
        anchor_period: str | None = None

        for event in events:
            handler = HANDLERS.get(event.event_type)
            if handler is None:
                if context.strict:
                    raise ReplayError(f"Unknown event type: {event.event_type} (event_id={event.event_id})")
                replay_warnings.append(
                    f"Skipped unknown event type '{event.event_type}' for event_id={event.event_id}."
                )
                continue

            state = handler(state, event, context)

            if event.event_type == "WORLD_INITIALIZED":
                raw_world_summary = event.payload.get("world_summary")
                if isinstance(raw_world_summary, dict):
                    world_summary = {
                        gu_code: values
                        for gu_code, values in raw_world_summary.items()
                        if isinstance(gu_code, str) and isinstance(values, dict)
                    }

                raw_participant_count = event.payload.get("participant_count")
                if isinstance(raw_participant_count, int):
                    participant_count = raw_participant_count

                raw_anchor_period = event.payload.get("anchor_period")
                if isinstance(raw_anchor_period, str):
                    anchor_period = raw_anchor_period

        state_has_full_core = all(
            key in state for key in ("intake_plan", "scenario", "participant_roster", "max_rounds")
        )
        completeness: Literal["partial", "full"] = (
            "full"
            if state_has_full_core
            and world_summary is not None
            and participant_count is not None
            and anchor_period is not None
            else "partial"
        )

        return ReplayResult(
            state=state,
            completeness=completeness,
            event_count=len(events),
            warnings=[*_state_warnings(state), *replay_warnings],
            world_summary=world_summary,
            participant_count=participant_count,
            anchor_period=anchor_period,
        )
