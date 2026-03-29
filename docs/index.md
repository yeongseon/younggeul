# Younggeul — 영끌 시뮬레이터

[![CI](https://github.com/yeongseon/younggeul/actions/workflows/ci.yml/badge.svg)](https://github.com/yeongseon/younggeul/actions)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/yeongseon/younggeul/blob/main/LICENSE)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)

**Younggeul** (영끌, *YOLO Mortgage Simulator*) is an open-source, agent-based Korean real estate simulation platform. It models Seoul apartment market dynamics through a deterministic data pipeline, a multi-agent LangGraph simulation, and evidence-gated reporting — every claim in a report is traceable to a real data source.

## Why Younggeul?

Korean housing discourse often mixes anecdote with data. Younggeul aims to make market analysis *auditable*: if a simulated agent says "prices are rising," the platform must produce a citation from an official dataset before that claim reaches the report.

## Key Features

| Feature | Description |
|---|---|
| **Evidence-Gated Reporting** | Every report claim must pass citation validation — no citation, no publication |
| **Multi-Agent Simulation** | LangGraph-based graph with buyer, investor, tenant, landlord, and broker agents |
| **Deterministic Data Pipeline** | Bronze → Silver → Gold ETL from MOLIT, BOK, and KOSTAT official sources |
| **100% Citation Coverage** | All Silver/Gold records carry source metadata; reports fail if coverage drops below threshold |
| **Immutable Snapshots** | SHA-256-verified dataset snapshots ensure reproducible simulation runs |

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                      younggeul CLI                       │
└────────────┬─────────────────────────────┬──────────────┘
             │                             │
    ┌────────▼────────┐          ┌─────────▼────────┐
    │   Data Plane    │          │ Simulation Plane  │
    │                 │          │                   │
    │  Bronze Layer   │          │  LangGraph Graph  │
    │  (Raw API data) │          │  (Multi-agent)    │
    │       ↓         │          │                   │
    │  Silver Layer   │──────────▶  Evidence Store  │
    │  (Pydantic)     │          │       ↓           │
    │       ↓         │          │  Citation Gate    │
    │  Gold Layer     │          │       ↓           │
    │  (Aggregated)   │          │  Report Renderer  │
    └────────┬────────┘          └───────────────────┘
             │
    ┌────────▼────────┐
    │    Snapshots    │
    │  (SHA-256 hash) │
    └─────────────────┘
```

## Quick Links

- **[Installation](getting-started/installation.md)** — Get up and running in minutes
- **[Quick Start](getting-started/quickstart.md)** — Run your first simulation
- **[CLI Reference](guide/cli.md)** — All commands explained
- **[Architecture Overview](architecture/overview.md)** — How the pieces fit together
- **[ADRs](adr/001-clean-room-development.md)** — Design decisions

## v0.1 Scope

v0.1 targets **Seoul apartment transactions only**, using fixture data so no API key is required for local development. Real data ingestion requires a [PublicDataReader](https://github.com/WooilJeong/PublicDataReader) API key from data.go.kr.
