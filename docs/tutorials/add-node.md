# How to Add a Simulation Node

## Overview

Simulation nodes are LangGraph node callables that read `SimulationGraphState`, compute one step, emit provenance events, and return partial state updates. In Younggeul, nodes are built via dependency-injected factories (`make_<node>_node(...)`) and then wired into `build_simulation_graph`. The intake planner is the canonical reference implementation.

## Prerequisites

- You understand LangGraph `StateGraph` basics (`add_node`, `add_edge`, `add_conditional_edges`).
- You know the required input keys your node needs from `SimulationGraphState`.
- You can run unit tests in `apps/kr-seoul-apartment/tests/unit`.

## Step 1: Understand the Graph State

`SimulationGraphState` (TypedDict) is the contract between nodes.

```python
from typing import Annotated, Any, TypedDict
import operator

from younggeul_core.state.simulation import (
    ActionProposal,
    ParticipantState,
    ReportClaim,
    RoundOutcome,
    RunMeta,
    ScenarioSpec,
    SegmentState,
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
```

Key idea: nodes return only changed keys; reducers (for `event_refs`, `warnings`, etc.) merge outputs over graph execution.

## Step 2: Create the Node Factory

Follow the `intake_planner.py` factory pattern: dependency injection + inner node callable.

```python
from __future__ import annotations

from typing import Any

from ..events import EventStore, SimulationEvent
from ..graph_state import SimulationGraphState
from ..llm.ports import LLMMessage, StructuredLLM
from ..schemas.intake import IntakePlan


def make_intake_planner_node(
    event_store: EventStore,
    structured_llm: StructuredLLM,
) -> Any:
    def node(state: SimulationGraphState) -> dict[str, Any]:
        from datetime import datetime, timezone
        from uuid import uuid4

        user_query = state.get("user_query", "")
        messages: list[LLMMessage] = [
            {"role": "system", "content": INTAKE_SYSTEM_PROMPT},
            {"role": "user", "content": user_query},
        ]

        plan = structured_llm.generate_structured(
            messages=messages,
            response_model=IntakePlan,
            temperature=0.0,
        )

        run_meta = state.get("run_meta")
        if run_meta is None:
            raise ValueError("run_meta is required before emitting simulation events")

        event_id = str(uuid4())
        event_store.append(
            SimulationEvent(
                event_id=event_id,
                run_id=run_meta.run_id,
                round_no=0,
                event_type="INTAKE_PLANNED",
                timestamp=datetime.now(timezone.utc),
                payload=plan.model_dump(),
            )
        )

        return {
            "intake_plan": plan.model_dump(),
            "event_refs": [event_id],
        }

    return node
```

When adding your own node, keep this structure:

- `make_<node>_node(...dependencies)` returns `node`.
- `node(state: SimulationGraphState) -> dict[str, Any]`.
- Read with `state.get(...)`.
- Validate required inputs and `raise ValueError` for missing invariants.
- Return only state updates.

## Step 3: Emit Events for Provenance

Every important node action should append a `SimulationEvent` and return its ID in `event_refs`.

```python
from datetime import datetime, timezone
from uuid import uuid4

from ..events import SimulationEvent

run_meta = state.get("run_meta")
if run_meta is None:
    raise ValueError("run_meta is required before emitting simulation events")

event_id = str(uuid4())
event_store.append(
    SimulationEvent(
        event_id=event_id,
        run_id=run_meta.run_id,
        round_no=state.get("round_no", 0),
        event_type="MY_NODE_COMPLETED",
        timestamp=datetime.now(timezone.utc),
        payload={"input_summary": "...", "result_summary": "..."},
    )
)

return {
    "event_refs": [event_id],
    # plus your node outputs
}
```

## Step 4: Register the Node in the Graph

Wire your node in `simulation/graph.py` with tracing and explicit edges.

```python
graph = StateGraph(SimulationGraphState)

intake_planner_node = make_intake_planner_node(event_store, structured_llm)
world_initializer_node = make_world_initializer_node(event_store, snapshot_reader)

graph.add_node("intake_planner", _traced_node("intake_planner", intake_planner_node))
graph.add_node("world_initializer", _traced_node("world_initializer", world_initializer_node))

graph.add_edge(START, "intake_planner")
graph.add_edge("intake_planner", "scenario_builder")
graph.add_conditional_edges(
    "world_initializer",
    _should_start_rounds,
    {
        "participant_decider": "participant_decider",
        "round_summarizer": "round_summarizer",
    },
)
```

The existing graph already uses this pattern for every node (`intake_planner`, `scenario_builder`, `world_initializer`, ...).

## Step 5: Write Unit Tests

Match `test_intake_planner.py`: seed state with `seed_graph_state`, inject fake ports, call node directly, assert state + events.

```python
from typing import Any

import pytest

from younggeul_app_kr_seoul_apartment.simulation.event_store import InMemoryEventStore
from younggeul_app_kr_seoul_apartment.simulation.graph_state import (
    SimulationGraphState,
    seed_graph_state,
)
from younggeul_app_kr_seoul_apartment.simulation.nodes.intake_planner import make_intake_planner_node
from younggeul_app_kr_seoul_apartment.simulation.schemas.intake import IntakePlan


class FakeStructuredLLM:
    def __init__(self, response: IntakePlan) -> None:
        self.response = response

    def generate_structured(self, **_: Any) -> IntakePlan:
        return self.response


def test_node_returns_updates_and_event_refs() -> None:
    store = InMemoryEventStore()
    plan = IntakePlan(
        user_query="강남구 아파트를 스트레스 테스트해줘",
        objective="금리 인상 시 가격 민감도를 확인한다.",
        analysis_mode="stress",
        geography_hint="강남구",
        segment_hint="아파트",
        horizon_months=12,
        requested_shocks=["금리인상"],
        participant_focus=["실수요자", "투자자"],
        constraints=["월 1회 업데이트"],
        assumptions=["정책 변화 없음"],
        ambiguities=["시작 시점이 불명확함"],
    )
    node = make_intake_planner_node(store, FakeStructuredLLM(plan))
    state = seed_graph_state(plan.user_query, "run-node-001", "run-node", "gpt-test")

    result = node(state)

    assert result["intake_plan"] == plan.model_dump()
    assert len(result["event_refs"]) == 1
    assert store.count("run-node-001") == 1


def test_node_raises_when_required_input_missing() -> None:
    store = InMemoryEventStore()
    minimal_plan = IntakePlan(
        user_query="강남구 분석",
        objective="시장 방향을 요약한다.",
        analysis_mode="baseline",
        geography_hint=None,
        segment_hint=None,
        horizon_months=12,
        requested_shocks=[],
        participant_focus=[],
        constraints=[],
        assumptions=[],
        ambiguities=[],
    )
    node = make_intake_planner_node(store, FakeStructuredLLM(minimal_plan))
    state: SimulationGraphState = {"user_query": "강남구 분석"}

    with pytest.raises(ValueError, match="run_meta is required"):
        node(state)
```

## Summary

Checklist:

- [ ] Identified required input/output keys in `SimulationGraphState`.
- [ ] Added `make_<node>_node(...dependencies)` with `node(state) -> dict[str, Any]`.
- [ ] Added invariant checks (`ValueError`) for required state inputs.
- [ ] Emitted `SimulationEvent` via `EventStore.append(...)` and returned `event_refs`.
- [ ] Registered node with `_traced_node` and connected edges (`add_edge` / `add_conditional_edges`).
- [ ] Added unit tests with `seed_graph_state`, fake ports, and direct node invocation.
