# Simulation

Younggeul's simulation plane is built on [LangGraph](https://github.com/langchain-ai/langgraph), a framework for building stateful, multi-actor graph workflows.

## Overview

A simulation takes a natural-language query (e.g., `"서울 강남구 아파트 시장 전망"`) and a set of Gold metrics as input, then produces a structured report with full evidence citations.

```bash
younggeul simulate \
  --query "서울 강남구 아파트 시장 전망" \
  --max-rounds 2 \
  --output-dir ./output/simulation
```

---

## Graph Topology

```
START
  ↓
intake_planner       # Parse query, identify target district/period
  ↓
scenario_builder     # Build scenario context from baseline forecast
  ↓
world_initializer    # Initialize participant agents and event store
  ↓
┌─── round loop (1..max_rounds) ─────────────────────┐
│   participant_node  (buyer, investor, tenant,        │
│                      landlord, broker)               │
│       ↓                                              │
│   round_resolver    # Aggregate decisions, update    │
│                     # market state                   │
│       ↓                                              │
│   continue_check    # Decide whether to run more     │
│                     # rounds                         │
└────────────────────────────────────────────────────-─┘
  ↓
evidence_builder     # Collect evidence records from event store
  ↓
report_writer        # Draft report claims from simulation state
  ↓
citation_gate        # Validate each claim has a citation
  ↓
report_renderer      # Render final Markdown + JSON report
  ↓
END
```

---

## Participant Agents

v0.1 uses **deterministic stub agents** — no LLM calls are made during simulation. Each agent applies rule-based logic against the current market state.

| Agent | Role | Decision Logic |
|-------|------|----------------|
| `buyer` | Prospective apartment buyer | Evaluates affordability vs. price trend |
| `investor` | Real estate investor | Evaluates ROI based on YoY metrics |
| `tenant` | Current renter | Evaluates rent-to-buy ratio |
| `landlord` | Property owner | Evaluates rental yield |
| `broker` | Market intermediary | Aggregates market signals |

---

## Simulation State

The graph uses a `SimulationGraphState` TypedDict with list reducers for append-only fields:

| Field | Type | Description |
|-------|------|-------------|
| `query` | `str` | Original simulation query |
| `scenario` | `ScenarioContext` | Parsed scenario from intake_planner |
| `rounds` | `list[RoundResult]` | Results per round (append-only) |
| `events` | `list[MarketEvent]` | Event store (append-only) |
| `evidence` | `list[EvidenceRecord]` | Evidence collected post-rounds |
| `report` | `RenderedReport \| None` | Final rendered report |

---

## Node Types

- **Deterministic nodes** — Pure functions, no external I/O (all v0.1 nodes)
- **Stub nodes** — Placeholder logic returning canned responses, used while LLM integration is deferred

!!! note
    LLM-backed nodes are scoped to v0.2. All v0.1 simulation logic is deterministic and fully testable without network access.
