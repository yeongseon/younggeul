# 영끌 시뮬레이터 (younggeul)

> **YOLO Mortgage Simulator** — Open-source, agent-based Korean real estate simulation platform

[![CI - Lint](https://github.com/yeongseon/younggeul/actions/workflows/lint.yml/badge.svg)](https://github.com/yeongseon/younggeul/actions/workflows/lint.yml)
[![CI - Test](https://github.com/yeongseon/younggeul/actions/workflows/test.yml/badge.svg)](https://github.com/yeongseon/younggeul/actions/workflows/test.yml)
[![CodeQL](https://github.com/yeongseon/younggeul/actions/workflows/codeql.yml/badge.svg)](https://github.com/yeongseon/younggeul/actions/workflows/codeql.yml)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)

Younggeul models Seoul apartment market dynamics through a **deterministic data pipeline**, a **multi-agent LangGraph simulation**, and **evidence-gated reporting** — every claim in a report is traceable to an official government data source.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        younggeul CLI                         │
│  ingest │ snapshot │ baseline │ simulate │ report │ eval     │
└────────────┬──────────────────────────────┬─────────────────┘
             │                              │
    ┌────────▼────────┐           ┌─────────▼─────────┐
    │   Data Plane    │           │  Simulation Plane  │
    │  (Deterministic)│           │    (LangGraph)     │
    │                 │           │                    │
    │  Bronze (Raw)   │           │  Multi-Agent Graph │
    │      ↓          │           │  5 participant     │
    │  Silver (Typed) │───────────▶  agents per round  │
    │      ↓          │           │       ↓            │
    │  Gold (Agg)     │           │  Evidence Store    │
    │      ↓          │           │       ↓            │
    │  Snapshots      │           │  Citation Gate     │
    │  (SHA-256)      │           │       ↓            │
    └─────────────────┘           │  Report Renderer   │
                                  └────────────────────┘
                                           │
                                  ┌────────▼────────┐
                                  │ Evaluation Plane │
                                  │  pytest -m eval  │
                                  │  3 scenarios     │
                                  │  83+ assertions  │
                                  └─────────────────┘
```

## Key Features

- **Evidence-Gated Reporting** — Every report claim must pass citation validation before publication
- **Multi-Agent Simulation** — LangGraph graph with buyer, investor, tenant, landlord, and broker agents
- **Deterministic Data Pipeline** — Bronze → Silver → Gold ETL from official Korean government sources
- **Immutable Snapshots** — SHA-256-verified dataset snapshots ensure reproducible simulation runs
- **Zero Hallucinations** — No LLMs in the data plane; all transforms are 100% deterministic

## Quick Start

```bash
# Install
pip install -e ".[dev,kr-seoul-apartment]"

# Run the full demo (fixture data, no API key needed)
make demo

# Or step by step:
younggeul ingest --output-dir ./output/pipeline
younggeul snapshot publish --data-dir ./output/pipeline --snapshot-dir ./output/snapshots
younggeul baseline --snapshot-dir ./output/snapshots --output-dir ./output/baseline
younggeul simulate --query "서울 강남구 아파트 시장 전망" --max-rounds 2 --output-dir ./output/simulation
younggeul report --report-file ./output/simulation/simulation_report_*.md
younggeul eval --output-dir ./eval_results
```

## Data Sources

| Source | Provider | Data |
|--------|----------|------|
| MOLIT 실거래가 | 국토교통부 | Apartment transaction prices |
| BOK ECOS | 한국은행 | Base interest rates |
| KOSTAT KOSIS | 통계청 | Population migration |

Data is accessed through [kpubdata](https://pypi.org/project/kpubdata/), a unified client for Korean public data APIs. v0.1 includes fixture data so no API key is needed for local development; live ingest is opt-in (see below).

### Live ingest (optional)

To fetch real data from MOLIT, BOK, and KOSTAT, set three API keys in your environment and use `--source live`:

```bash
export KPUBDATA_DATAGO_API_KEY=...   # data.go.kr (MOLIT RTMS)
export KPUBDATA_BOK_API_KEY=...      # 한국은행 ECOS
export KPUBDATA_KOSIS_API_KEY=...    # 통계청 KOSIS

younggeul ingest --source live --gu 11680 --month 202503 --output-dir ./output/live
```

`--gu` is a 5-digit MOLIT sigungu code (e.g. `11680` = 강남구) and `--month` is `YYYYMM`. To populate YoY/MoM change ratios in the Gold output, fetch multiple months in one invocation via `--months`:

```bash
# Year-over-year (same month, different years)
younggeul ingest --source live --gu 11680 --months 202403,202503 --output-dir ./output/live-yoy

# Month-over-month (consecutive months)
younggeul ingest --source live --gu 11680 --months 202502,202503 --output-dir ./output/live-mom
```

For cross-district analysis, use `--gus` (CSV) instead of `--gu`:

```bash
younggeul ingest --source live --gus 11680,11440 --months 202403,202503 --output-dir ./output/live-multi
```

`--month`/`--months` and `--gu`/`--gus` are each mutually exclusive. Live mode populates MOLIT trades, BOK base rate, **and** KOSTAT 시도-level net migration (joined to each gu via `gu_code[:2]`). See [ADR-007](docs/adr/007-kpubdata-live-ingest.md) for the live ingest design and [ADR-008](docs/adr/008-kostat-live-activation.md) for the KOSTAT activation rationale.

To chain ingest → snapshot publish → baseline against real APIs in one shot:

```bash
set -a; source .env; set +a   # load KPUBDATA_* keys
make demo-live                # or: GU=11680 MONTHS=202403,202503 bash scripts/demo_live.sh
```

## v0.1 Scope

- **Region**: Seoul apartments only (서울 아파트 매매)
- **Granularity**: District/month level (`gu_month`)
- **Output**: Directional prediction + evidence-gated markdown report
- **CLI**: 6 commands — `ingest`, `snapshot`, `baseline`, `simulate`, `report`, `eval`
- **Tests**: 1,100+ tests across unit, integration, contract, behavioral, and robustness suites
- **Observability**: OpenTelemetry tracing (opt-in), CodeQL security analysis

## Project Structure

```
younggeul/
├── core/                        # Platform-agnostic schemas and protocols
│   └── src/younggeul_core/
├── apps/kr-seoul-apartment/     # Seoul apartment implementation
│   └── src/younggeul_app_kr_seoul_apartment/
│       ├── connectors/          # MOLIT, BOK, KOSTAT data connectors
│       ├── normalizers/         # Bronze → Silver transforms
│       ├── aggregator/          # Silver → Gold aggregation
│       ├── simulation/          # LangGraph nodes, graph, events
│       └── cli.py               # Click-based CLI
├── docs/                        # MkDocs Material documentation
│   ├── adr/                     # Architecture Decision Records
│   ├── architecture/            # Architecture guides
│   ├── getting-started/         # Installation, quickstart, demo
│   └── guide/                   # CLI, pipeline, simulation, eval
├── scripts/                     # Demo and utility scripts
└── .github/workflows/           # CI/CD workflows
```

**Dependency direction**: `core` ← `apps` (never reversed)

## Development

```bash
# Install dev dependencies
pip install -e ".[dev,kr-seoul-apartment]"

# Lint
make lint

# Run tests
make test          # unit tests only
make test-all      # all tests including integration

# Format
make format

# Build docs
pip install -e ".[docs]"
make docs-serve    # http://localhost:8000
```

## Design Decisions

Key architectural decisions are documented as ADRs:

| ADR | Decision |
|-----|----------|
| [ADR-001](docs/adr/001-clean-room-development.md) | Clean-room development under Apache-2.0 |
| [ADR-002](docs/adr/002-monorepo-boundaries.md) | Monorepo with strict package boundaries |
| [ADR-003](docs/adr/003-immutable-dataset-snapshots.md) | SHA-256 immutable dataset snapshots |
| [ADR-004](docs/adr/004-langgraph-boundaries.md) | No `add_messages`; typed state only |
| [ADR-005](docs/adr/005-evidence-gated-reporting.md) | Three-phase evidence-gated reporting |
| [ADR-006](docs/adr/006-public-data-policy.md) | No raw data in git; manifests only |
| [ADR-007](docs/adr/007-kpubdata-live-ingest.md) | Live ingest via kpubdata unified client |
| [ADR-008](docs/adr/008-kostat-live-activation.md) | Activate KOSTAT migration at 시도 granularity |

## License

[Apache-2.0](LICENSE)
