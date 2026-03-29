# Architecture Overview

Younggeul is organized into **three planes** that have strict dependency boundaries.

## Three-Plane Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        Data Plane                            │
│  Bronze (raw) → Silver (typed) → Gold (aggregated)          │
│  Snapshots (immutable, SHA-256)                              │
└────────────────────────────┬─────────────────────────────────┘
                             │ GoldDistrictMonthlyMetrics
                             ▼
┌──────────────────────────────────────────────────────────────┐
│                     Simulation Plane                         │
│  LangGraph graph  →  Event store  →  Evidence store         │
│  Citation gate    →  Report renderer                         │
└────────────────────────────┬─────────────────────────────────┘
                             │ RenderedReport
                             ▼
┌──────────────────────────────────────────────────────────────┐
│                     Evaluation Plane                         │
│  pytest-based eval  →  Canonical scenarios  →  CI checks    │
└──────────────────────────────────────────────────────────────┘
```

---

## Monorepo Layout

```
younggeul/
├── core/                          # Shared domain types and protocols
│   └── src/younggeul_core/
│       ├── state/                 # Bronze/Silver/Gold/Simulation TypedDicts
│       ├── storage/               # Snapshot protocol
│       └── evidence/              # EvidenceRecord types
├── apps/
│   └── kr-seoul-apartment/        # Seoul apartment implementation
│       └── src/younggeul_app_kr_seoul_apartment/
│           ├── cli.py             # Click entry point
│           ├── pipeline/          # Bronze→Silver→Gold connectors
│           ├── simulation/        # LangGraph graph, nodes
│           └── reporting/         # Citation gate, renderer
├── docs/                          # Documentation (this site)
├── eval_cases/                    # YAML eval fixtures
├── scripts/                       # demo.sh
├── mkdocs.yml
└── pyproject.toml
```

---

## Dependency Direction

```
younggeul_core  ←  younggeul_app_kr_seoul_apartment
    (shared)           (Seoul-specific)
```

`core` has **no dependency** on any app. Apps depend on core but not on each other.

---

## Key Design Principles

| Principle | What it means |
|-----------|---------------|
| **Deterministic data plane** | Same input → same output; no LLMs in ETL |
| **No LLMs in ETL** | Bronze/Silver/Gold transformations are pure functions |
| **Evidence-gated reporting** | Reports only publish if citation coverage ≥ 100% |
| **Immutable snapshots** | Pipeline outputs are content-addressed and hash-verified |
| **Contract-first** | Pydantic models define the schema; tests enforce it |

See the individual architecture pages for deeper dives:

- [Data Plane](data-plane.md)
- [Simulation Plane](simulation-plane.md)
- [Evidence-Gated Reporting](reporting.md)
