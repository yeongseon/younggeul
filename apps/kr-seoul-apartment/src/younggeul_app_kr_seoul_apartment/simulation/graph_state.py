from __future__ import annotations

import operator
from datetime import datetime, timezone
from typing import Annotated, Any, TypedDict

from pydantic import TypeAdapter, ValidationError
from typing_extensions import TypedDict as ExtTypedDict

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


class SimulationGraphState(TypedDict, total=False):
    user_query: str
    intake_plan: dict[str, Any]

    run_meta: RunMeta
    snapshot: SnapshotRef
    scenario: ScenarioSpec
    round_no: int
    max_rounds: int
    world: dict[str, SegmentState]
    participants: dict[str, ParticipantState]
    governance_actions: dict[str, ActionProposal]
    market_actions: dict[str, ActionProposal]
    last_outcome: RoundOutcome | None

    event_refs: Annotated[list[str], operator.add]
    evidence_refs: Annotated[list[str], operator.add]
    report_claims: Annotated[list[ReportClaim], operator.add]
    warnings: Annotated[list[str], operator.add]


class _SimulationStateAdapterSchema(ExtTypedDict):
    run_meta: RunMeta
    snapshot: SnapshotRef
    scenario: ScenarioSpec
    round_no: int
    max_rounds: int
    world: dict[str, SegmentState]
    participants: dict[str, ParticipantState]
    governance_actions: dict[str, ActionProposal]
    market_actions: dict[str, ActionProposal]
    last_outcome: RoundOutcome | None
    event_refs: list[str]
    evidence_refs: list[str]
    report_claims: list[ReportClaim]
    warnings: list[str]


_SIMULATION_STATE_ADAPTER: TypeAdapter[SimulationState] = TypeAdapter(_SimulationStateAdapterSchema)
_SIMULATION_STATE_KEYS = set(SimulationState.__annotations__)
_REQUIRED_INITIALIZED_KEYS = {
    "run_meta",
    "snapshot",
    "scenario",
    "world",
    "participants",
    "round_no",
    "max_rounds",
}


def seed_graph_state(user_query: str, run_id: str, run_name: str, model_id: str) -> SimulationGraphState:
    return {
        "user_query": user_query,
        "run_meta": RunMeta(
            run_id=run_id,
            run_name=run_name,
            created_at=datetime.now(timezone.utc),
            model_id=model_id,
        ),
        "event_refs": [],
        "evidence_refs": [],
        "report_claims": [],
        "warnings": [],
    }


def to_simulation_state(graph_state: SimulationGraphState) -> SimulationState:
    if not validate_initialized_state(graph_state):
        raise ValueError("Simulation graph state is not initialized")

    simulation_payload = {key: value for key, value in graph_state.items() if key in _SIMULATION_STATE_KEYS}
    try:
        validated = _SIMULATION_STATE_ADAPTER.validate_python(simulation_payload)
    except ValidationError as exc:
        raise ValueError("Simulation graph state cannot be converted to SimulationState") from exc
    return validated


def validate_initialized_state(graph_state: SimulationGraphState) -> bool:
    state_dict: dict[str, object] = dict(graph_state)
    return all(key in state_dict and state_dict[key] is not None for key in _REQUIRED_INITIALIZED_KEYS)
