# ADR-012: Adopt abdp-backed compatibility architecture for younggeul_core

## Status
Accepted

## Date
2026-04-23

## Context

`younggeul/core/src/younggeul_core/` (~1,200 LOC) has grown into a small in-house framework that provides simulation state schemas, data-pipeline contracts, connector plumbing, snapshot manifests, and evidence/claim primitives. Every one of these subsystems now has a near-identical, more general counterpart in [`agent-based-decision-pipeline`](https://github.com/yeongseon/agent-based-decision-pipeline) (`abdp`), an upstream OSS framework released as v0.3.0 ("Auditable Simulation Milestone") with 833 passing tests and an explicit auditable-simulation contract.

A direct surface comparison:

| younggeul_core subsystem | abdp public surface |
|---|---|
| `state/simulation.py` (`ScenarioSpec`, `SegmentState`, `ParticipantState`, `SimulationState`, `SnapshotRef`) | `abdp.simulation.{ScenarioSpec, SegmentState, ParticipantState, SimulationState, SnapshotRef, ActionProposal}` |
| `state/{bronze,silver,gold}.py` | `abdp.data.{BronzeContract, SilverContract, GoldContract}` |
| `storage/snapshot.py` (`SnapshotManifest`) | `abdp.data.{SnapshotManifest, SnapshotTier}` |
| `connectors/{protocol,retry,manifest,hashing}.py` | `abdp.core.{Connector, retry, Backoff, ManifestFactory, stable_hash}` and friends |
| `evidence/schemas.py` (`Evidence`, `Claim`, `Gate`) | `abdp.evidence.{EvidenceRecord, ClaimRecord, AuditLog, EvidenceStore, InMemoryEvidenceStore}` |

Without a deliberate decision, three drifts are likely to compound:

1. Continued duplication of framework-like code in `younggeul_core/` that has nothing Korean-real-estate-specific in it.
2. Subtle semantic divergence between the local types and the upstream types as both evolve, foreclosing a future migration.
3. Loss of the auditability/replay primitives `abdp` already provides (`AuditLog`, deterministic `ScenarioRunner`, `evaluate_metrics`/`evaluate_gates`, `render_{json,markdown}_report`) because we keep growing parallel local equivalents.

At the same time, two facts make a wholesale cutover unsafe today:

- `abdp` ships a v0.3.0 git tag whose `abdp.__version__` is still `0.1.0.dev0`. The public API is stabilizing but is not version-pinned in the conventional sense.
- younggeul currently has 1,178 tests across 63 files and a shipped v0.3.0 release. The simulation runtime is built on LangGraph (conditional edges, multi-node fan-out, two LLM-driven nodes) — an execution model that does not map onto `abdp`'s deterministic `ScenarioRunner` step-loop without a non-trivial rewrite.

We therefore need an architectural stance that captures the duplication win without betting v0.3.0 behavior or 1,178 tests on a paradigm rewrite plus an immature framework surface.

## Decision

Adopt an **adapter-layer architecture** (Option C in the design review). Specifically:

1. `younggeul_core/*` stays as the **stable public API** that all app code, the CLI, and tests import from. No app file is asked to learn about `abdp`.
2. The internals of `younggeul_core/*` delegate to a pinned `abdp` commit, behind an `_compat` module that selects between a `local` backend (today's hand-written impls) and an `abdp` backend (re-exports/wrappers).
3. The default simulation engine remains LangGraph for the v0.3.x line. An `abdp.scenario.ScenarioRunner`-based engine is introduced later as an **experimental, non-default** second engine, only after parity with the LangGraph engine is demonstrated under the existing eval suite.
4. Auditability, evaluation, and reporting primitives from `abdp` are wired in as an **optional render path** behind a CLI flag (`--render abdp|legacy`, default `legacy`), so the existing report behavior cannot regress silently.

The migration is broken into ten independently shippable work items tracked as GitHub issues #236–#245 under epic #235. Each work item is independently revertible via the backend flag and is gated on the parity-suite expansion (issue #241).

### Alternatives considered

- **Option A — Full migration.** Replace `younggeul_core` with `abdp` outright and rewrite the LangGraph engine onto `abdp.scenario.ScenarioRunner`. Rejected for this iteration: it couples three risks at once — pinning to an immature framework version, a package-wide API churn that touches 1,178 tests, and an execution-model rewrite (LangGraph → `ScenarioRunner`) that cannot be validated incrementally. Re-evaluated when the criteria in *Consequences → Exit criteria* below are met.

- **Option B — Bridge-only.** Keep `younggeul_core` and LangGraph untouched; only translate the LangGraph run output into `abdp.evidence.AuditLog` at the boundary. Rejected as a terminal state: it preserves all duplication permanently and turns the bridge into a maintenance liability. Acceptable only as an interim step inside Option C (covered by the LangGraph→AuditLog adapter work).

## Consequences

### Positive

- **Bounded blast radius per work item.** App code does not change; only `younggeul_core` internals do. Each work item is a small, reviewable diff with a parity test.
- **Net code reduction.** When the connectors-hashing adoption (#238), the data-aliases adoption (#239), and the simulation-overlap refactor land, ~600 LOC of `core/` becomes thin re-exports/wrappers; the final cleanup then deletes the legacy implementations after parity is proven.
- **Auditability surface comes for free.** `abdp.evidence.AuditLog`, `abdp.evaluation.{evaluate_metrics, evaluate_gates}`, and `abdp.reporting.render_{json,markdown}_report` become available behind the optional render path without rewriting our renderer.
- **No paradigm bet.** LangGraph stays the production engine; the `ScenarioRunner` engine is a parallel, opt-in track that can be abandoned without affecting v0.3.x.
- **Reversible.** The `YOUNGGEUL_CORE_BACKEND={local,abdp}` flag lets us switch backends per-process without code changes.

### Negative

- **Two-stack interim period.** Until the selective-adoption finalization (issue #245), both `local` and `abdp` backends ship. The compat layer adds a small amount of indirection.
- **External version pin.** We pin a specific `abdp` commit, not a published PyPI version. Upgrades require a deliberate parity rerun.
- **Bridge code risks becoming permanent** if the shadow-runner work (#244) or the selective-adoption finalization (#245) stalls. Mitigation: every adapter-introducing work item has a paired cleanup criterion in the epic's risk register.

### Exit criteria for revisiting Option A

A full Option A cutover (drop `younggeul_core`, replace LangGraph with `ScenarioRunner`) becomes appropriate only when **all three** of the following are true:

1. `abdp` publishes a stable, semver-versioned release on PyPI (no more `0.1.0.dev0` mismatch).
2. younggeul has a concrete need for multi-engine simulation that LangGraph alone cannot satisfy.
3. The experimental `ScenarioRunner` engine from the shadow-runner work (issue #244) has matched the LangGraph engine's outputs under the full eval suite (`pytest -m eval`) in shadow mode for at least one minor release.

Until then, the stance is: **C now, A later if earned.**

## Risk register

1. **Semantic mismatch in "near-identical" types.** Local and `abdp` Pydantic models may validate or serialize differently in edge cases. *Mitigation:* the parity-suite expansion (issue #241) introduces a parametrized suite asserting byte-identical JSON dumps and equivalent validation behavior across both backends.
2. **`abdp` version instability** (tag `v0.3.0` vs internal `0.1.0.dev0`). *Mitigation:* pin a specific commit SHA in `pyproject.toml`; isolate every `abdp` import behind `_compat`; upstream fixes asynchronously.
3. **Behavior drift in simulation outputs.** Even with matching types, report content or event sequences could shift. *Mitigation:* keep LangGraph default; the shadow-runner work (issue #244) adds shadow-mode parity tests on event count, final state, and rendered report semantics before any engine flip.
4. **Bridge code becoming permanent.** Adapter layers tend to outlive their stated purpose. *Mitigation:* the LangGraph→AuditLog adapter work has a paired removal criterion in the selective-adoption finalization (issue #245); every adapter-introducing PR must reference its cleanup issue.
5. **LangGraph removal scope creep.** LangGraph is currently a hard dependency wired into the web layer, the CLI, and many tests. *Mitigation:* defer any LangGraph removal until after shadow `ScenarioRunner` parity is independently demonstrated; treat removal as a separate post-finalization decision.

## Implementation milestones

| Label | Issue | Title | Size |
|---|---|---|---|
| ADR | #236 | ADR-012 (this document) | S |
| Backend switch | #237 | Add internal abdp backend switch | M |
| Connectors hashing | #238 | Delegate `connectors/{hashing,retry,manifest,protocol}` → `abdp.core` | S |
| Data aliases | #239 | Delegate `state/{bronze,silver,gold}` + `storage/snapshot` → `abdp.data` | M |
| Simulation overlap | #240 | Refactor `state/simulation` into abdp overlap + extensions | M |
| Parity suite | #241 | Contract-parity test suite (local vs abdp) | M |
| AuditLog adapter | #242 | LangGraph run → `abdp.evidence.AuditLog` adapter | M |
| Reporting render flag | #243 | Optional `--render abdp` CLI path | M |
| Shadow runner | #244 | Prototype `ScenarioRunner` engine (experimental) | L |
| Finalization | #245 | Remove duplicated legacy core after default flip | M |

## Amendment (2026-04-23) — selective-adoption scope correction

Hands-on inspection during the data-aliases adoption (issue #239) and a follow-up Oracle consult revealed that several "near-identical" entries in the surface-comparison table above are *named* the same as `abdp` types but model fundamentally different concepts. The migration plan is therefore revised as follows. The original architectural decision (Option C — adapter layer) stands; only the per-work-item scope changes.

**Binding scope corrections:**

- **`state/{bronze,silver,gold}.py` are NOT replaced.** `abdp.data.{Bronze,Silver,Gold}Contract` are abstract structural `Protocol[RowT]` types with only `manifest` / `rows`. The local schemas are concrete Pydantic models for the Korean apartment domain (e.g. `BronzeAptTransaction` carries 32 MOLIT fields). They remain younggeul-owned.
- **`storage/snapshot.SnapshotManifest` is NOT replaced.** `abdp.data.SnapshotManifest` is a per-tier UUID-keyed dataclass with parent-pointer lineage; ours is a Pydantic multi-table dataset manifest with sha256-derived `dataset_snapshot_id`. Different concept under the same name. It remains younggeul-owned.
- **`connectors/{retry,manifest,protocol}` adaptation is permanently abandoned** (issue #238 closed). `abdp.core.retry` is a decorator factory with a different invocation contract; `abdp.core.ManifestFactory` produces abdp `SnapshotManifest`, not `BronzeIngestManifest`. Only `connectors/hashing.sha256_payload` was successfully delegated to `abdp.core.stable_hash` (the connectors-hashing adoption, merged).
- **The LangGraph→AuditLog adapter work (issue #242, deferred and absorbed into #244) is deferred to the shadow-runner work (issue #244)** (2026-04-23 follow-up Oracle re-consult). `abdp.evidence.AuditLog` is a frozen dataclass whose `__post_init__` enforces `scenario_key == run.scenario_key` and `seed == run.seed`, where `Seed = NewType("Seed", int)`. younggeul has no integer seed, no `scenario_key`, no per-step `SimulationState` snapshots, and no UUID-keyed `SnapshotRef`. Building an AuditLog now would force inventing all of those, contradicting the binding rule "don't invent public IDs to satisfy Protocols (keep synthesis private to the shadow-runner adapters)." The shadow `ScenarioRunner` in the shadow-runner work (issue #244) produces `ScenarioRun` / `Seed` / `scenario_key` / per-step `SimulationState` natively, so the AuditLog projection happens there with real provenance, not synthetic. **The reporting render-flag work (issue #243, PR #251) becomes the next shippable work item** because reporting needs only formatting compatibility, not simulation-provenance compatibility.
- **The selective-adoption finalization (issue #245) no longer flips the default backend or targets ~600 LOC of deletions.** The success gate becomes "framework logic adopted where semantics actually match, with parity tests covering each adopted surface."

**Revised work-item map:**

| Label | Issue | Revised deliverable |
|---|---|---|
| Data aliases | [#239](https://github.com/kpubdata-lab/younggeul/issues/239) | `_compat.data` re-exports of `Bronze/Silver/GoldContract`, `SnapshotTier`, `AbdpSnapshotManifest` only. Schemas + storage manifest stay local. |
| LangGraph→AuditLog adapter work (deferred and absorbed) | ~~[#242](https://github.com/kpubdata-lab/younggeul/issues/242)~~ | **Deferred to the shadow-runner work (issue #244)** (2026-04-23 Oracle re-consult). Producing an `abdp.evidence.AuditLog` from the current LangGraph run output requires synthesizing public IDs (`Seed: int`, `scenario_key`, `SnapshotRef.snapshot_id: UUID`, deterministic evidence/claim UUIDs) and per-step `SimulationState` snapshots LangGraph does not record. The shadow `ScenarioRunner` in the shadow-runner work produces all of these natively, so the AuditLog adapter becomes a thin projection there instead of public-ID synthesis here. |
| Reporting render flag | [#243](https://github.com/kpubdata-lab/younggeul/issues/243) | ✅ **Shipped** in [PR #251](https://github.com/kpubdata-lab/younggeul/pull/251). `--render abdp\|legacy` CLI flag on `simulate`, delegating to `abdp.reporting.render_json_report` over `RenderedReport.model_dump(mode="json")`. Markdown remains the byte-identical default. |
| Simulation fit-gap doc | [#240](https://github.com/kpubdata-lab/younggeul/issues/240) | **Doc-only** (Oracle 2026-04-23): [`docs/architecture/abdp-simulation-fit-gap.md`](../architecture/abdp-simulation-fit-gap.md). Full surface inventory + per-field gap classification + per-surface shadow-runner/finalization landing plan, used as the build-spec for the shadow-runner work. No `state/simulation.py` change, no Protocol re-exports, no overlap parity test (every overlap surface is `public-ID-bearing` and would require pre-shadow-runner synthesis). |
| Parity suite expansion | [#241](https://github.com/kpubdata-lab/younggeul/issues/241) | Expanded parity suite covering every adopted surface (excludes AuditLog until the shadow-runner work). |
| Shadow runner | [#244](https://github.com/kpubdata-lab/younggeul/issues/244) | Shadow-mode `ScenarioRunner` **and** the real `AuditLog` adapter absorbed from #242. LangGraph stays the default execution engine. Shipped in three PRs: PR #254 (ID helpers), PR #255 (scenario adapter), and PR #256 (shadow runner). |
| Finalization | [#245](https://github.com/kpubdata-lab/younggeul/issues/245) | ✅ **Shipped.** Selective-adoption finalization. **No default flip.** Doc and CI hardening only — no code/module removal owed (remaining local surfaces are intentionally younggeul-owned domain types and the LangGraph runtime, not duplicate framework code). See "Final selective-adoption inventory" below. |

### Final selective-adoption inventory

The 2026-04-23 finalization ruling (Oracle, recorded in this amendment) closed out the selective-adoption epic without flipping the default backend and without deleting any local module. The inventory below freezes the per-surface adoption decision and the parity tests that gate it. Future changes to this inventory require a new ADR or amendment.

**Adopted surfaces (delegated to `abdp` and gated by parity tests)**

| Surface | Local site | abdp target | Parity test |
|---|---|---|---|
| Payload hashing | `core/connectors/hashing.py::sha256_payload` | `abdp.core.stable_hash` | `core/tests/contract/test_compat_hashing_parity.py` |
| Bronze/Silver/Gold contract aliases | `core/_compat/data.py::{BronzeContract, SilverContract, GoldContract, SnapshotTier, AbdpSnapshotManifest}` | `abdp.data` re-exports | `core/tests/contract/test_compat_data_aliases.py` |
| JSON report renderer | `core/_compat/reporting.py::render_json_report` | `abdp.reporting.render_json_report` | `core/tests/contract/test_compat_reporting.py`, `apps/kr-seoul-apartment/tests/unit/test_cli_render_flag.py` |
| Deterministic ID helpers | `core/_compat/ids.py::{derive_scenario_key, derive_snapshot_uuid, SnapshotIdRegistry}` | `abdp.simulation` ID contract (`scenario_key`, `Seed`, `SnapshotRef.snapshot_id` UUID) | `core/tests/contract/test_compat_ids.py` |
| Scenario / participant / action / segment adapters + shadow `AuditLog` projection | `core/_compat/scenario.py::{AbdpSegmentAdapter, AbdpParticipantAdapter, AbdpActionAdapter, CallableAgent, CallableResolver, to_abdp_snapshot_ref, to_abdp_simulation_state, project_audit_log}` and `apps/.../simulation/shadow_runner.py::run_shadow_audit` | `abdp.simulation.{SegmentState, ParticipantState, ActionProposal, ScenarioRunner}`, `abdp.evidence.AuditLog` | `core/tests/contract/test_compat_scenario.py`, `apps/kr-seoul-apartment/tests/integration/test_simulate_cli_shadow_audit.py` |

**Retained local by design (NOT delegated)**

| Surface | Rationale |
|---|---|
| `core/storage/snapshot.py::{SnapshotManifest, SnapshotTableEntry}` | younggeul's snapshot manifest models the Korean-public-data ingest layout (Bronze tables keyed by `gu_code`/`month`, MOLIT/BOK/KOSTAT provenance fields). `abdp.data.SnapshotManifest` models a generic decision-pipeline snapshot ref. The shapes are not interchangeable; bridging via `_compat/data.py::AbdpSnapshotManifest` is sufficient at the boundary. |
| `core/state/{bronze,silver,gold}.py` | Korean apartment domain types (apartment trades, base rate, net-migration). The `abdp.data.{Bronze,Silver,Gold}Contract` aliases in `_compat/data.py` cover the framework-facing typing needs without forcing the domain models out of younggeul. |
| `core/state/simulation.py` | younggeul's `SimulationState` is the LangGraph TypedDict consumed by the runtime. `abdp.simulation.SimulationState` is a Protocol used at the shadow-runner boundary. The shadow runner (`apps/.../simulation/shadow_runner.py`) projects the LangGraph state into the abdp Protocol; the canonical in-memory representation stays local. |
| `apps/kr-seoul-apartment/src/younggeul_app_kr_seoul_apartment/simulation/` (LangGraph runtime — nodes, graph, events) | This is the production execution engine and the default code path under `YOUNGGEUL_CORE_BACKEND=local`. The shadow runner runs alongside it via `simulate --shadow-audit-log` for `AuditLog` provenance; replacing LangGraph would be a separate post-finalization decision. |

**CI hardening shipped with the finalization**

- `.github/workflows/test.yml` matrix simplified to `backend: [local, abdp]`; both legs install `[dev,kr-seoul-apartment,abdp]`.
- Test scope changed from `pytest -m "not slow and not integration"` to `pytest -m "not slow and not live"` so the shadow-runner integration test (`test_simulate_cli_shadow_audit`) and other integration coverage actually execute on every push.
- Guardrail test `test_default_backend_remains_local` in `core/tests/contract/test_compat_guardrails.py` enforces `DEFAULT_BACKEND == "local"` at the source level — a default flip now requires a new ADR/amendment, not a constant rename.

The `YOUNGGEUL_CORE_BACKEND={local,abdp}` flag introduced in the backend-switch work (issue #237) still selects between local and adapter-routed code paths where adoption succeeded; the flag's default remains `local` indefinitely.

## References

- Epic: [#235 — Adopt abdp framework for younggeul_core](https://github.com/kpubdata-lab/younggeul/issues/235)
- Upstream: [yeongseon/agent-based-decision-pipeline](https://github.com/yeongseon/agent-based-decision-pipeline)
- Upstream v0.3.0 release: [Auditable Simulation Milestone](https://github.com/yeongseon/agent-based-decision-pipeline/releases/tag/v0.3.0)
- Related: [ADR-002 Monorepo Boundaries](002-monorepo-boundaries.md), [ADR-004 LangGraph Boundaries](004-langgraph-boundaries.md), [ADR-005 Evidence-Gated Reporting](005-evidence-gated-reporting.md)
