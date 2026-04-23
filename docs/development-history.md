# Development Journey: v0.1 Release

How the **영끌 시뮬레이터 (YOLO Mortgage Simulator)** went from an empty
repository to a fully released v0.1.0 in eleven phases.

---

## Background

Younggeul was born from a desire to build an **open-source, agent-based real
estate simulation platform** focused on the Korean housing market. An earlier
internal project, MiroFish, had explored similar problems but was tightly
coupled to proprietary services and licensed under AGPL-3.0.

To start fresh, the team adopted a **clean-room development** process
([ADR-001](adr/001-clean-room-development.md)): zero code inheritance from
MiroFish, original prompt engineering, and a fully portable Apache-2.0
licensed codebase.

### Guiding Principles

- **Official data only** — All data flows through Korean government APIs
  (MOLIT 실거래가, BOK 금리, KOSTAT 인구이동).
  See [ADR-006](adr/006-public-data-policy.md).
- **Deterministic data plane** — No LLMs in the Bronze → Silver → Gold
  pipeline. Every transform is reproducible.
  See [ADR-004](adr/004-langgraph-boundaries.md).
- **Agent-based simulation** — Market participants (buyer, investor, tenant,
  landlord, broker) operate through a LangGraph orchestration graph.
- **Evidence-gated reporting** — Every claim in the output report must cite
  traceable evidence.
  See [ADR-005](adr/005-evidence-gated-reporting.md).
- **Issue-driven workflow** — Every feature, fix, and decision went through
  GitHub Issues → branch → PR → CI → squash merge.

---

## Foundation & Scaffolding (12 issues)

The first milestone established the repository skeleton.

**What we built:**

- Monorepo layout with two packages: `core/` (platform-agnostic schemas and
  protocols) and `apps/kr-seoul-apartment/` (Korea-specific application).
  See [ADR-002](adr/002-monorepo-boundaries.md).
- CI workflows: `lint.yml` (ruff + mypy), `test.yml` (pytest), `codeql.yml`.
- `pyproject.toml` with editable installs and development dependencies.
- `Makefile` targets for common development commands.
- Initial documentation site with MkDocs Material.

**Key decisions:**

- Chose a monorepo over separate repos to keep schema definitions co-located
  with their consumers while maintaining clean package boundaries.
- Selected Pydantic v2 as the data modeling foundation for its speed and
  native JSON Schema support.

**Lessons learned:**

- Getting the package boundary between `core/` and `apps/` right early saved
  enormous refactoring later. The rule: "If it's specific to Korean real
  estate, it goes in `apps/`."

---

## Contracts & Schemas (8 issues)

Data contracts came before any implementation — a deliberate choice that paid
off throughout the project.

**What we built:**

- Bronze, Silver, and Gold Pydantic schemas in `core/`.
- Simulation state schemas (RunMeta, ScenarioSpec, ParticipantState, etc.).
- Evidence and snapshot schemas.
- 165 contract tests validating serialization round-trips and field
  constraints.

**Key decisions:**

- Bronze schemas use `str | None` for every field — conservative parsing that
  defers type coercion to the Silver layer.
- Strict mypy in `core/`, relaxed in `apps/` — the schemas are the type
  safety boundary.

**Lessons learned:**

- Writing contract tests first was tedious but caught dozens of field naming
  inconsistencies before any pipeline code existed.

---

## Data Plane — Bronze (17 issues)

The first real data flowing through the system.

**What we built:**

- Connector protocol (`Connector` abstract base class with `fetch()` method).
- Three government API connectors: MOLIT (apartment transactions), BOK
  (interest rates), KOSTAT (migration statistics).
- Rate limiting, retry logic, and content-addressable file hashing.
- Ingest manifest tracking for reproducibility.

**Key decisions:**

- Used `PublicDataReader` (공공데이터) as the HTTP client rather than raw
  `requests` — it handles the quirks of Korean government API pagination.
- Every connector fetch produces a deterministic file hash, enabling cache
  invalidation and snapshot integrity checks.

**Lessons learned:**

- Korean government APIs have undocumented pagination limits and inconsistent
  date formats. Defensive parsing in Bronze connectors saved debugging time
  downstream.

---

## Data Plane — Silver & Entity Resolution (11 issues)

Cleaning and typing the raw Bronze data.

**What we built:**

- Silver normalizers: `silver_apt.py` (11 transform functions),
  `silver_macro.py` (8 transform functions).
- Entity resolution for matching apartment complex names across data sources.
- Data quality scoring (completeness, validity, consistency checks).

**Key decisions:**

- Every Silver transform is a pure function: `BronzeRecord → SilverRecord`.
  No side effects, no state, no network calls.
- Quality scores are computed inline during normalization, not as a separate
  pass.

**Lessons learned:**

- The `derive_gu_code()` and `derive_gu_name()` functions for mapping Korean
  legal district codes to human-readable names required careful handling of
  edge cases (merged districts, renamed areas).

---

## Data Plane — Gold & Baseline (14 issues)

Aggregation and the first analytical output.

**What we built:**

- Gold aggregator producing `GoldDistrictMonthlyMetrics` at `gu_month`
  granularity.
- Trend enrichment (YoY/MoM price changes, volume changes).
- Immutable snapshot system with SHA-256 content-addressed manifests.
  See [ADR-003](adr/003-immutable-dataset-snapshots.md).
- Baseline statistical forecaster (trend extrapolation, no ML).

**Key decisions:**

- Snapshots are immutable and content-addressed. A snapshot ID is the SHA-256
  hash of all its constituent table hashes. This means any data change
  produces a new snapshot ID — no silent mutations.
- The baseline forecaster deliberately uses simple statistics (moving
  averages, linear extrapolation) rather than ML models. This keeps the data
  plane fully deterministic and auditable.

**Lessons learned:**

- The snapshot system became the foundation for simulation reproducibility —
  every simulation run references a specific snapshot ID, making results
  traceable to exact input data.

---

## Simulation Plane — Core Runtime (14 issues)

The simulation engine skeleton.

**What we built:**

- `SimulationGraphState` with TypedDict and `operator.add` reducers for
  LangGraph compatibility.
- Intake planner, scenario builder, and world initializer nodes.
- Event store with append-only semantics (in-memory and file-backed).
- Graph builder composing nodes into a LangGraph `StateGraph`.

**Key decisions:**

- Used LangGraph `StateGraph` over alternatives (AutoGen, CrewAI) for its
  explicit graph semantics, TypedDict state, and deterministic execution.
  See [ADR-004](adr/004-langgraph-boundaries.md).
- Node factory pattern (`make_*_node()`) allows dependency injection of LLM
  clients, snapshot readers, and configuration without global state.

**Lessons learned:**

- LangGraph's `operator.add` reducer for list fields (events, claims) is
  elegant but requires discipline — every node must return deltas, not full
  state.

---

## Simulation Plane — Participant Agents (21 issues)

The largest milestone, bringing the market to life.

**What we built:**

- Five heuristic participant policies: `BuyerPolicy`, `InvestorPolicy`,
  `TenantPolicy`, `LandlordPolicy`, `BrokerPolicy`.
- `ParticipantPolicy` protocol with `decide()` method.
- Policy registry mapping roles to implementations.
- Participant decider node orchestrating all agents per round.
- Round resolver aggregating individual decisions into market outcomes.
- Continue gate with configurable max rounds.
- Round summarizer generating per-round narrative events.

**Key decisions:**

- Policies are heuristic-first (rule-based) with an LLM escape hatch via the
  `StructuredLLM` port. In v0.1.0, all policies are deterministic — LLM
  integration is deferred to v0.2.
- The round loop uses LangGraph conditional edges rather than Python while
  loops, keeping execution fully within the graph framework.

**Lessons learned:**

- 21 issues was too many for a single milestone. Future milestones should cap
  at ~15 issues to maintain focus.
- The `SegmentDelta` / `ParticipantDelta` split (market-level vs.
  individual-level) was crucial for clean round resolution.

---

## Report & Evidence Pipeline (11 issues)

Turning simulation data into trustworthy output.

**What we built:**

- Evidence builder extracting simulation, segment, participant, and round
  facts from the event stream.
- Report writer generating structured `ReportClaim` objects.
- Citation gate validating every claim against the evidence store.
  See [ADR-005](adr/005-evidence-gated-reporting.md).
- Report renderer producing JSON and Markdown output.

**Key decisions:**

- Failed citation checks don't crash the pipeline — they exclude the claim
  from the final report and emit a warning. This "soft failure" approach
  maintains output quality without losing the entire report.
- Evidence records use UUIDs and SHA-256 hashes for identity, enabling
  cross-referencing between claims and their supporting data.

**Lessons learned:**

- The evidence-gated approach caught several subtle bugs where simulation
  nodes were emitting events with incorrect metadata. The citation gate
  effectively acts as a second layer of integration testing.

---

## Evaluation Plane (10 issues)

Systematic quality assurance.

**What we built:**

- pytest-based evaluation framework with `@pytest.mark.eval` markers.
- Three canonical scenarios: Gangnam bull market, Seocho baseline, Gangnam
  stress test.
- Contract eval tests (schema compliance, field constraints).
- Behavioral eval tests (directional correctness, policy consistency).
- Robustness eval tests (edge cases, missing data resilience).
- Nightly GitHub Actions workflow running the full eval suite.

**Key decisions:**

- Eval tests are separate from unit tests (`pytest -m eval`) and run nightly
  rather than on every push. This keeps CI fast while providing daily quality
  signals.
- Canonical scenarios are frozen snapshots of real data, ensuring eval
  stability across code changes.

**Lessons learned:**

- The behavioral tests (e.g., "buyer confidence should decrease when interest
  rates spike") proved more valuable than schema tests for catching
  regressions in policy logic.

---

## Observability & Security (4 issues)

Production readiness foundations.

**What we built:**

- OpenTelemetry manual instrumentation for all 12 simulation nodes.
- `trace_node()` decorator with span attributes (node name, round number,
  participant count).
- Tracing gated by `OTEL_ENABLED` environment variable — zero overhead when
  disabled.
- CodeQL security analysis with `security-extended` query suite.

**Key decisions:**

- Manual instrumentation over auto-instrumentation. LangGraph's internal
  structure doesn't map cleanly to automatic span creation, so explicit
  `trace_node()` wrappers give more meaningful traces.
- CodeQL runs on every push to `main` and on PRs, catching security issues
  before merge.

**Lessons learned:**

- The 4-issue milestone was refreshingly focused after the Participant Agents phase's 21 issues.
  Smaller milestones with clear scope are more productive.

---

## v0.1 Release (10 issues)

Packaging everything for public use.

**What we built:**

- Click-based CLI with 6 commands: `ingest`, `snapshot`, `baseline`,
  `simulate`, `report`, `eval`.
- End-to-end demo script (`make demo` / `scripts/demo.sh`).
- MkDocs Material documentation site (14 pages).
- README with badges, architecture diagram, and quickstart.
- CHANGELOG following Keep a Changelog format.
- Release workflow: lint → test → build → GitHub Release on `v*` tag.
- Docs deployment workflow: build → GitHub Pages on push to `main`.

**Key decisions:**

- Click over Typer for CLI — Click's decorator model is more explicit and
  doesn't require runtime type introspection.
- The release workflow is fully automated: push a `v*` tag and GitHub Actions
  builds wheels, creates a release, and publishes docs.

**Lessons learned:**

- Writing the demo script forced us to exercise the entire pipeline
  end-to-end, which caught several integration issues that unit tests missed.

---

## By the Numbers

| Metric | Value |
|--------|-------|
| Phases completed | 11 (Foundation → v0.1 Release) |
| Issues closed | 132 |
| Pull requests merged | 60+ |
| Tests passing | 1,111+ |
| Contract tests | 165 |
| Architecture Decision Records | 6 |
| Documentation pages | 14 |
| Python packages | 2 (`younggeul-core`, `younggeul-app-kr-seoul-apartment`) |
| Data connectors | 3 (MOLIT, BOK, KOSTAT) |
| Simulation graph nodes | 12 |
| Participant agent types | 5 |
| CLI commands | 6 |

---

## What's Next

With v0.1.0 released, the project continues with:

- **Documentation hardening** — Docstring backfill, API reference generation,
  developer tutorials, and ADR expansion.
- **v0.2 planning** — Web UI, LLM-powered participant policies,
  LiteLLM + OTEL integration, Grafana observability dashboard.

The foundation is solid. The data plane is deterministic. The simulation is
reproducible. Now it's time to make it useful.
