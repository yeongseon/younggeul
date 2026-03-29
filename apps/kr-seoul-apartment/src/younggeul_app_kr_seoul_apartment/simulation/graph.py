from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from younggeul_core.state.simulation import (
    ParticipantState,
    ReportClaim,
    ScenarioSpec,
    SegmentState,
    SnapshotRef,
)

from .events import EventStore, SimulationEvent
from .graph_state import SimulationGraphState
from .llm.ports import StructuredLLM
from .nodes.continue_gate import should_continue
from .nodes.intake_planner import make_intake_planner_node
from .nodes.participant_decider import make_participant_decider_node
from .nodes.round_resolver import make_round_resolver_node
from .nodes.scenario_builder import make_scenario_builder_node
from .nodes.world_initializer import make_world_initializer_node
from .ports.snapshot_reader import SnapshotReader

DEFAULT_MAX_ROUNDS = 3


def build_simulation_graph(
    event_store: EventStore,
    *,
    default_max_rounds: int = DEFAULT_MAX_ROUNDS,
    structured_llm: StructuredLLM | None = None,
    snapshot_reader: SnapshotReader | None = None,
) -> CompiledStateGraph[Any, Any, Any, Any]:
    graph = StateGraph(SimulationGraphState)

    intake_planner_node = (
        make_intake_planner_node(event_store, structured_llm)
        if structured_llm is not None
        else _make_intake_planner_stub(event_store)
    )
    scenario_builder_node = (
        make_scenario_builder_node(event_store, structured_llm, snapshot_reader)
        if structured_llm is not None and snapshot_reader is not None
        else _make_scenario_builder_stub(event_store)
    )
    world_initializer_node = (
        make_world_initializer_node(event_store, snapshot_reader)
        if snapshot_reader is not None
        else _make_world_initializer_stub(event_store, default_max_rounds)
    )
    participant_decider_node = make_participant_decider_node(event_store)
    round_resolver_node = make_round_resolver_node(event_store)

    graph.add_node("intake_planner", intake_planner_node)
    graph.add_node("scenario_builder", scenario_builder_node)
    graph.add_node("world_initializer", world_initializer_node)
    graph.add_node("participant_decider", participant_decider_node)
    graph.add_node("round_resolver", round_resolver_node)
    graph.add_node("report_writer", _make_report_writer_stub(event_store))
    graph.add_node("critic", _make_passthrough_stub(event_store, "critic"))
    graph.add_node("citation_gate", _make_passthrough_stub(event_store, "citation_gate"))

    graph.add_edge(START, "intake_planner")
    graph.add_edge("intake_planner", "scenario_builder")
    graph.add_edge("scenario_builder", "world_initializer")
    graph.add_conditional_edges(
        "world_initializer",
        _should_start_rounds,
        {
            "participant_decider": "participant_decider",
            "report_writer": "report_writer",
        },
    )
    graph.add_edge("participant_decider", "round_resolver")
    graph.add_conditional_edges(
        "round_resolver",
        _route_after_resolve,
        {
            "participant_decider": "participant_decider",
            "report_writer": "report_writer",
        },
    )
    graph.add_edge("report_writer", "critic")
    graph.add_edge("critic", "citation_gate")
    graph.add_edge("citation_gate", END)

    return graph.compile()


def _should_start_rounds(state: SimulationGraphState) -> Literal["participant_decider", "report_writer"]:
    round_no = state.get("round_no", 0)
    max_rounds = state.get("max_rounds", DEFAULT_MAX_ROUNDS)
    return "participant_decider" if round_no < max_rounds else "report_writer"


def _route_after_resolve(state: SimulationGraphState) -> Literal["participant_decider", "report_writer"]:
    return "participant_decider" if should_continue(state) == "continue" else "report_writer"


def _append_event(
    event_store: EventStore,
    state: SimulationGraphState,
    event_type: str,
    *,
    round_no: int | None = None,
    payload: dict[str, Any] | None = None,
) -> str:
    event_id = str(uuid4())
    run_meta = state.get("run_meta")
    if run_meta is None:
        msg = "run_meta is required before emitting simulation events"
        raise ValueError(msg)

    event = SimulationEvent(
        event_id=event_id,
        run_id=run_meta.run_id,
        round_no=state.get("round_no", 0) if round_no is None else round_no,
        event_type=event_type,
        timestamp=datetime.now(timezone.utc),
        payload={} if payload is None else payload,
    )
    event_store.append(event)
    return event_id


def _make_intake_planner_stub(event_store: EventStore) -> Any:
    def node(state: SimulationGraphState) -> dict[str, Any]:
        event_id = _append_event(event_store, state, "INTAKE_PLANNED")
        user_query = state.get("user_query", "")
        return {
            "intake_plan": {
                "query": user_query,
                "planner_status": "stub",
            },
            "event_refs": [event_id],
        }

    return node


def _make_scenario_builder_stub(event_store: EventStore) -> Any:
    def node(state: SimulationGraphState) -> dict[str, Any]:
        event_id = _append_event(event_store, state, "SCENARIO_BUILT")
        return {
            "scenario": ScenarioSpec(
                scenario_name="Stub Scenario",
                target_gus=["11680"],
                target_period_start=date(2026, 1, 1),
                target_period_end=date(2026, 12, 31),
                shocks=[],
            ),
            "event_refs": [event_id],
        }

    return node


def _make_world_initializer_stub(event_store: EventStore, default_max_rounds: int) -> Any:
    def node(state: SimulationGraphState) -> dict[str, Any]:
        max_rounds = state.get("max_rounds", default_max_rounds)
        snapshot = state.get("snapshot") or SnapshotRef(
            dataset_snapshot_id="0" * 64,
            created_at=datetime.now(timezone.utc),
            table_count=1,
        )
        world = state.get("world") or {
            "11680": SegmentState(
                gu_code="11680",
                gu_name="강남구",
                current_median_price=2_000_000,
                current_volume=100,
                price_trend="flat",
                sentiment_index=0.7,
                supply_pressure=0.0,
            )
        }
        participants = state.get("participants") or {
            "p-001": ParticipantState(
                participant_id="p-001",
                role="buyer",
                capital=1_000_000_000_000,
                holdings=0,
                sentiment="neutral",
                risk_tolerance=0.5,
            ),
            "p-002": ParticipantState(
                participant_id="p-002",
                role="investor",
                capital=0,
                holdings=100,
                sentiment="neutral",
                risk_tolerance=0.5,
            ),
        }

        event_id = _append_event(
            event_store,
            state,
            "WORLD_INITIALIZED",
            round_no=0,
            payload={"max_rounds": max_rounds},
        )
        return {
            "snapshot": snapshot,
            "world": world,
            "participants": participants,
            "round_no": 0,
            "max_rounds": max_rounds,
            "governance_actions": {},
            "market_actions": {},
            "last_outcome": None,
            "event_refs": [event_id],
        }

    return node


def _make_report_writer_stub(event_store: EventStore) -> Any:
    def node(state: SimulationGraphState) -> dict[str, Any]:
        claim_id = str(uuid4())
        event_id = _append_event(event_store, state, "REPORT_WRITTEN", payload={"claim_id": claim_id})
        return {
            "report_claims": [
                ReportClaim(
                    claim_id=claim_id,
                    claim_json={"summary": "stub report"},
                    evidence_ids=[],
                    gate_status="passed",
                    repair_count=0,
                )
            ],
            "event_refs": [event_id],
        }

    return node


def _make_passthrough_stub(event_store: EventStore, name: str) -> Any:
    def node(state: SimulationGraphState) -> dict[str, Any]:
        event_id = _append_event(event_store, state, name.upper())
        return {"event_refs": [event_id]}

    return node
