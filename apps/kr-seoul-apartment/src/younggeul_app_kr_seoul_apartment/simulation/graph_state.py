# pyright: reportMissingImports=false

"""Graph-state schema helpers for simulation orchestration."""

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
    """Mutable state payload passed between simulation graph nodes."""

    user_query: str
    intake_plan: dict[str, Any]
    participant_roster: dict[str, Any]

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


def seed_graph_state(
    user_query: str,
    run_id: str,
    run_name: str,
    model_id: str,
    snapshot: SnapshotRef | None = None,
    scenario: ScenarioSpec | None = None,
    participant_roster: dict[str, Any] | None = None,
) -> SimulationGraphState:
    """Create an initial graph state for a simulation run.

    Args:
        user_query: Original user query for the simulation.
        run_id: Stable run identifier.
        run_name: Human-readable run name.
        model_id: Model identifier used for the run.
        snapshot: Optional preselected snapshot reference.
        scenario: Optional preseeded scenario specification.
        participant_roster: Optional preseeded participant roster payload.

    Returns:
        Seed graph state with run metadata and empty accumulators.
    """
    state: SimulationGraphState = {
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

    if snapshot is not None:
        state["snapshot"] = snapshot
    if scenario is not None:
        state["scenario"] = scenario
    if participant_roster is not None:
        state["participant_roster"] = participant_roster

    return state


def to_simulation_state(graph_state: SimulationGraphState) -> SimulationState:
    """Convert initialized graph state into a validated SimulationState.

    Args:
        graph_state: Graph state to convert.

    Returns:
        Validated simulation state payload.

    Raises:
        ValueError: When required fields are missing or schema validation fails.
    """
    if not validate_initialized_state(graph_state):
        raise ValueError("Simulation graph state is not initialized")

    simulation_payload = {key: value for key, value in graph_state.items() if key in _SIMULATION_STATE_KEYS}
    try:
        validated = _SIMULATION_STATE_ADAPTER.validate_python(simulation_payload)
    except ValidationError as exc:
        raise ValueError("Simulation graph state cannot be converted to SimulationState") from exc
    return validated


def validate_initialized_state(graph_state: SimulationGraphState) -> bool:
    """Check whether required graph-state fields are initialized.

    Args:
        graph_state: Graph state to validate.

    Returns:
        ``True`` when all required initialized keys are present and non-null.
    """
    state_dict: dict[str, object] = dict(graph_state)
    return all(key in state_dict and state_dict[key] is not None for key in _REQUIRED_INITIALIZED_KEYS)
