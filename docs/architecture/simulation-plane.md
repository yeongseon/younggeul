# Simulation Plane

The simulation plane executes a multi-agent market simulation using [LangGraph](https://github.com/langchain-ai/langgraph) and produces evidence-gated reports.

## SimulationGraphState

The entire simulation state is a `TypedDict` with append-only reducers for list fields:

```python
class SimulationGraphState(TypedDict):
    query: str                              # User's market query
    scenario: ScenarioContext               # Parsed scenario
    snapshot_id: str                        # Input data snapshot
    baseline: BaselineForecast              # Pre-computed baseline
    rounds: Annotated[list[RoundResult], operator.add]
    events: Annotated[list[MarketEvent], operator.add]
    evidence: Annotated[list[EvidenceRecord], operator.add]
    claims: Annotated[list[ReportClaim], operator.add]
    report: RenderedReport | None
    citation_gate_passed: bool
```

---

## Node Implementations

### `intake_planner`

Parses the query to extract `target_gu`, `time_horizon`, and `scenario_type`.

### `scenario_builder`

Constructs a `ScenarioContext` from baseline data and query parameters.

### `world_initializer`

Initializes the event store and participant agent states.

### Participant Nodes

Each participant is a separate node that reads current market state and appends `MarketEvent` objects:

```
buyer_node → investor_node → tenant_node → landlord_node → broker_node
```

All run within the round loop. v0.1 uses deterministic stubs.

### `round_resolver`

Aggregates participant events into a `RoundResult` and updates market state.

### `continue_check`

A conditional edge function — returns `"next_round"` or `"finish"` based on round count and convergence.

### `evidence_builder`

Scans the event store and Gold metrics to construct `EvidenceRecord` objects for each data reference.

### `report_writer`

Drafts `ReportClaim` objects from the simulation result, linking each claim to evidence IDs.

### `citation_gate`

Validates that every `ReportClaim` has a matching `EvidenceRecord`. Sets `citation_gate_passed = True/False`.

### `report_renderer`

Renders the final `RenderedReport` containing:
- `markdown: str` — Human-readable report
- `json: dict` — Structured report with claim/evidence linkage

---

## Graph Wiring

The graph is assembled in `graph.py`:

```python
builder = StateGraph(SimulationGraphState)
builder.add_node("intake_planner", intake_planner)
# ... all nodes ...
builder.add_conditional_edges("continue_check", route_rounds)
graph = builder.compile()
```

---

## OTEL Tracing

Each node is instrumented with OpenTelemetry spans:

```python
with tracer.start_as_current_span("node.intake_planner") as span:
    span.set_attribute("query", state["query"])
    # ... node logic
```

Traces are emitted to the configured OTEL exporter (stdout by default in v0.1).

---

## Node Factory Pattern

Nodes that share structure (participants) are created via a factory:

```python
def make_participant_node(role: ParticipantRole) -> NodeFn:
    def node(state: SimulationGraphState) -> SimulationGraphState:
        ...
    return node
```
