# Product Requirements Document (PRD): 영끌 시뮬레이터 (younggeul)

## 1. Overview
**영끌 시뮬레이터 (YOLO Mortgage Simulator)** is an open-source, agent-based Korean real estate simulation platform. It enables users to simulate market dynamics and predict housing price trends based on rigorous, evidence-based analysis using official government datasets.

## 2. Problem Statement
The Korean real estate market is notoriously opaque and influenced by speculative sentiment. Existing analysis tools are often:
- **Paywalled**: Restricted to institutional investors or paying subscribers.
- **Lacking Transparency**: Proprietary "black-box" models with no visibility into underlying assumptions.
- **Hallucination-Prone**: LLM-based tools often invent data points or citations.

There is a critical need for an open-source, evidence-gated simulation platform that uses only official government data to provide verifiable market insights.

## 3. Target Users
- **Individual Homebuyers**: Assessing entry timing and risk.
- **Real Estate Investors**: Simulating portfolio scenarios.
- **Researchers & Policy Analysts**: Evaluating the impact of interest rates or demographic shifts.

## 4. Product Vision
To provide an agent-based simulation platform that:
- Ingests official Korean government data via the kpubdata unified client (MOLIT, BOK, KOSIS).
- Runs multi-agent market simulations via LangGraph.
- Produces evidence-gated reports with zero hallucinations and 100% citation coverage.

## 5. v0.1 Scope (KR Seoul Apartment)
### In-Scope
- **Region**: Seoul apartments only (서울 아파트 매매).
- **Granularity**: `gu_month` level (district/month).
- **Output**: Directional prediction (Rise/Fall/Stable) and volume prediction.
- **Data Sources**:
  - MOLIT Actual Transaction Price (국토교통부 실거래가)
  - BOK Interest Rates (한국은행 금리)
  - KOSTAT Population Migration (통계청 인구이동)

### Out-of-Scope
- Rental markets (전월세).
- Commercial real estate (상업용).
- Nationwide coverage (non-Seoul regions).
- Real-time streaming predictions.
- Using Seoul Real Estate Information Plaza (서울부동산정보광장) as ground truth.

## 6. Key Features (Milestones)
- **Data Contracts & Schemas**: Define Bronze/Silver/Gold data tiers using Pydantic v2.
- **Data Connectors**: Integration with `data.go.kr` (MOLIT), BOK ECOS, and KOSIS via the [kpubdata](https://pypi.org/project/kpubdata/) unified client (see ADR-007).
- **Data Pipeline**: Deterministic ETL (Bronze → Silver → Gold) without LLM intervention.
- **Snapshot System**: Immutable datasets with `dataset_snapshot_id` and SHA-256 verification (Reference: ADR-003).
- **Simulation Core**: LangGraph state machine combining 5 LLM agents and 5 deterministic nodes (Reference: ADR-004).
- **Evidence & Reporting**: JSON-first claim generation followed by a citation gate and prose rendering (Reference: ADR-005).
- **Evaluation**: Regression testing using promptfoo benchmarks and golden datasets.
- **Observability**: Full tracing with OpenTelemetry and LangSmith.
- **CLI & API**: Management via `typer` CLI and `FastAPI` endpoints.
- **Release & Documentation**: Public release with comprehensive user guides.

## 7. Architecture Overview
The system follows a three-plane separation architecture:
1. **Data Plane (Deterministic)**: Handles ETL and snapshotting.
2. **Simulation Plane (LangGraph)**: Manages agent interactions and state transitions.
3. **Evaluation Plane (promptfoo)**: Validates output accuracy and safety.

### Project Structure (Monorepo)
- `core/`: Shared simulation engine and state management.
- `apps/kr-seoul-apartment/`: Seoul-specific data connectors and agent configurations.
- `benchmarks/kr-housing/`: promptfoo configurations and golden datasets.

### LangGraph Topology
`START` → `intake_planner` (LLM) → `snapshot_resolver` (Det) → `scenario_builder` (LLM) → `init_world` (Det) → `round_router` → [`policy_agent`, `bank_agent`] → `apply_governance` (Det) → [`buyer`, `investor`, `tenant`, `landlord`, `broker`] → `market_engine` (Det) → `round_summarizer` (Det) → `round_router` OR `finalize` → `report_writer_json_first` (LLM) → `citation_gate` (Det) → `repair_loop` (LLM) → `final_renderer` (Det) → `END`

## 8. Tech Stack
- **Languages**: Python 3.12+
- **Frameworks**: Pydantic v2, LangGraph, FastAPI
- **LLM Ops**: vLLM, LiteLLM, promptfoo, LangSmith
- **Observability**: OpenTelemetry
- **Tooling**: uv (package manager), ruff (linting), mypy (typing), pytest

## 9. Non-Functional Requirements
- **Reproducibility**: Every simulation run must be pinned to a `dataset_snapshot_id`.
- **No Hallucinations**: Mandatory evidence-gated reporting where every claim must map to a data source (Reference: ADR-005).
- **Clean-room Development**: Zero inheritance from legacy MiroFish codebase (Reference: ADR-001).
- **Data Policy**: No raw government data files committed to Git (Reference: ADR-006).
- **CI/CD**: GitHub Actions for linting, testing, and automated data pipeline runs.

## 10. Success Metrics for v0.1
- **Directional Accuracy**: ≥60% on held-out test sets.
- **Citation Coverage**: 100% (Every claim in a report must have a valid citation).
- **Reproducibility**: 100% success rate in recreating outputs from a snapshot ID.
- **Latency**: <5 minutes wall-clock time for a single-gu simulation.

## 11. Constraints & Limitations
- **Ground Truth**: Do not use "서울부동산정보광장" as the primary ground truth for validation.
- **Compute**: Public PRs will not trigger self-hosted GPU runners automatically.
- **Iterative Approach**: Do not attempt nationwide or multi-asset simulation in the initial phase.
