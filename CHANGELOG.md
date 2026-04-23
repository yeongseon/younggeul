# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **abdp selective adoption finalized (issue #245, epic #235).** `younggeul_core`
  now adopts `agent-based-decision-pipeline` selectively where semantics
  match: hashing delegation, deterministic JSON report rendering
  (`simulate --render abdp`), shadow audit-log generation
  (`simulate --shadow-audit-log`), and runner-internal scenario/snapshot
  ID derivation. The default backend remains `local`; the abdp backend
  is opt-in via `YOUNGGEUL_CORE_BACKEND=abdp`. See
  [ADR-012](docs/adr/012-abdp-backed-core.md) for the final selective-adoption inventory.

### Added

- `simulate --shadow-audit-log <PATH>` CLI flag emits a frozen
  `abdp.evidence.AuditLog` JSON in parallel with the LangGraph run, by
  driving the same participant policies and round resolver through
  `abdp.scenario.ScenarioRunner` (no decision-logic fork) (issue #244).
- `simulate --render abdp` CLI flag renders the simulation report JSON
  via `abdp.reporting.render_json_report`. Markdown remains the
  byte-identical default (issue #243, PR #251).
- `core/_compat/{ids,scenario,reporting,data}` adapter modules wrapping
  the abdp surfaces consumed by the shadow runner and the reporting
  flag. All synthesized identifiers (Seed, scenario_key, snapshot UUID,
  proposal_id) are runner-internal and never appear in the markdown
  report or CLI summary text.
- Two-backend parity coverage in `core/tests/contract/test_compat_*`
  exercising every adopted surface across `local` and `abdp`.

## [0.1.0] - 2026-03-29

### Added

#### Data Plane
- Bronze/Silver/Gold Pydantic v2 data schemas with 165 contract tests
- MOLIT (실거래가), BOK (금리), KOSTAT (인구이동) data connectors via PublicDataReader
- Silver normalizers for apartment transactions, interest rates, and migration data
- Gold aggregator producing district-monthly metrics (`gu_month` granularity)
- Trend enrichment with YoY/MoM price and volume change calculations
- Immutable snapshot system with SHA-256 content-addressed manifests
- Baseline statistical forecaster

#### Simulation Plane
- LangGraph-based multi-agent simulation graph (12 nodes)
- Typed `SimulationGraphState` with `operator.add` reducers
- Five participant agent types: buyer, investor, tenant, landlord, broker
- Deterministic round resolution with configurable max rounds
- Event store (in-memory and file-backed) with append-only semantics
- Evidence store with kind/subject indexing

#### Evidence-Gated Reporting
- Evidence builder extracting simulation/segment/participant/round facts
- Deterministic report writer generating structured `ReportClaim` objects
- Citation gate validating evidence IDs and context matching
- Report renderer producing JSON + Markdown output
- Failed claims excluded from output; visible in warnings

#### Evaluation
- pytest-based evaluation plane with `pytest -m eval` marker
- Three canonical eval scenarios (gangnam bull, seocho baseline, gangnam stress)
- Contract, behavioral, and robustness eval test suites
- Nightly eval GitHub Actions workflow

#### Observability & Security
- OpenTelemetry manual instrumentation for all simulation nodes
- Tracing gated by `OTEL_ENABLED` environment variable (zero overhead when off)
- CodeQL security analysis with `security-extended` query suite

#### CLI & Demo
- Click-based CLI with 6 commands: `ingest`, `snapshot`, `baseline`, `simulate`, `report`, `eval`
- JSON output mode (`--output json`)
- End-to-end demo script (`make demo` / `scripts/demo.sh`)

#### Documentation
- MkDocs Material documentation site (14 pages)
- 6 Architecture Decision Records (ADR-001 through ADR-006)
- Full CLI reference, getting started guide, architecture documentation

#### Infrastructure
- Monorepo structure: `core/` + `apps/kr-seoul-apartment/`
- GitHub Actions CI: lint (ruff + mypy), test (pytest), CodeQL, nightly eval
- 1,100+ tests across unit, integration, contract, behavioral, and robustness suites

[0.1.0]: https://github.com/yeongseon/younggeul/releases/tag/v0.1.0
