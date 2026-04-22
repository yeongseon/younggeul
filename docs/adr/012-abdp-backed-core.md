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

The migration is broken into ten independently shippable milestones (M1–M10) tracked as GitHub issues #236–#245 under epic #235. Each milestone is independently revertible via the backend flag and is gated on a parity test suite (M6).

### Alternatives considered

- **Option A — Full migration.** Replace `younggeul_core` with `abdp` outright and rewrite the LangGraph engine onto `abdp.scenario.ScenarioRunner`. Rejected for this iteration: it couples three risks at once — pinning to an immature framework version, a package-wide API churn that touches 1,178 tests, and an execution-model rewrite (LangGraph → `ScenarioRunner`) that cannot be validated incrementally. Re-evaluated when the criteria in *Consequences → Exit criteria* below are met.

- **Option B — Bridge-only.** Keep `younggeul_core` and LangGraph untouched; only translate the LangGraph run output into `abdp.evidence.AuditLog` at the boundary. Rejected as a terminal state: it preserves all duplication permanently and turns the bridge into a maintenance liability. Acceptable only as an interim step inside Option C (covered by M7).

## Consequences

### Positive

- **Bounded blast radius per milestone.** App code does not change; only `younggeul_core` internals do. Each milestone is a small, reviewable diff with a parity test.
- **Net code reduction.** When M3–M5 land, ~600 LOC of `core/` becomes thin re-exports/wrappers; M10 deletes the legacy implementations after parity is proven.
- **Auditability surface comes for free.** `abdp.evidence.AuditLog`, `abdp.evaluation.{evaluate_metrics, evaluate_gates}`, and `abdp.reporting.render_{json,markdown}_report` become available behind the optional render path without rewriting our renderer.
- **No paradigm bet.** LangGraph stays the production engine; the `ScenarioRunner` engine is a parallel, opt-in track that can be abandoned without affecting v0.3.x.
- **Reversible.** The `YOUNGGEUL_CORE_BACKEND={local,abdp}` flag lets us switch backends per-process without code changes.

### Negative

- **Two-stack interim period.** Until M10, both `local` and `abdp` backends ship. The compat layer adds a small amount of indirection.
- **External version pin.** We pin a specific `abdp` commit, not a published PyPI version. Upgrades require a deliberate parity rerun.
- **Bridge code (M7) risks becoming permanent** if M9/M10 stall. Mitigation: every adapter-introducing milestone has a paired cleanup criterion in the epic's risk register.

### Exit criteria for revisiting Option A

A full Option A cutover (drop `younggeul_core`, replace LangGraph with `ScenarioRunner`) becomes appropriate only when **all three** of the following are true:

1. `abdp` publishes a stable, semver-versioned release on PyPI (no more `0.1.0.dev0` mismatch).
2. younggeul has a concrete need for multi-engine simulation that LangGraph alone cannot satisfy.
3. The experimental `ScenarioRunner` engine from M9 has matched the LangGraph engine's outputs under the full eval suite (`pytest -m eval`) in shadow mode for at least one minor release.

Until then, the stance is: **C now, A later if earned.**

## Risk register

1. **Semantic mismatch in "near-identical" types.** Local and `abdp` Pydantic models may validate or serialize differently in edge cases. *Mitigation:* M6 introduces a parametrized parity suite asserting byte-identical JSON dumps and equivalent validation behavior across both backends.
2. **`abdp` version instability** (tag `v0.3.0` vs internal `0.1.0.dev0`). *Mitigation:* pin a specific commit SHA in `pyproject.toml`; isolate every `abdp` import behind `_compat`; upstream fixes asynchronously.
3. **Behavior drift in simulation outputs.** Even with matching types, report content or event sequences could shift. *Mitigation:* keep LangGraph default; M9 adds shadow-mode parity tests on event count, final state, and rendered report semantics before any engine flip.
4. **Bridge code becoming permanent.** Adapter layers tend to outlive their stated purpose. *Mitigation:* M7's adapter has a paired removal criterion in M10; every adapter-introducing PR must reference its cleanup issue.
5. **LangGraph removal scope creep.** LangGraph is currently a hard dependency wired into the web layer, the CLI, and many tests. *Mitigation:* defer any LangGraph removal until after M9 ScenarioRunner parity is independently demonstrated; treat removal as a separate post-M10 decision.

## Implementation milestones

| # | Issue | Title | Size |
|---|---|---|---|
| M1 | #236 | ADR-012 (this document) | S |
| M2 | #237 | Add internal abdp backend switch | M |
| M3 | #238 | Delegate `connectors/{hashing,retry,manifest,protocol}` → `abdp.core` | S |
| M4 | #239 | Delegate `state/{bronze,silver,gold}` + `storage/snapshot` → `abdp.data` | M |
| M5 | #240 | Refactor `state/simulation` into abdp overlap + extensions | M |
| M6 | #241 | Contract-parity test suite (local vs abdp) | M |
| M7 | #242 | LangGraph run → `abdp.evidence.AuditLog` adapter | M |
| M8 | #243 | Optional `--render abdp` CLI path | M |
| M9 | #244 | Prototype `ScenarioRunner` engine (experimental) | L |
| M10 | #245 | Remove duplicated legacy core after default flip | M |

## Amendment (2026-04-23) — M4'–M10' scope correction

Hands-on inspection during M4 and a follow-up Oracle consult revealed that several "near-identical" entries in the surface-comparison table above are *named* the same as `abdp` types but model fundamentally different concepts. The migration plan is therefore revised as follows. The original architectural decision (Option C — adapter layer) stands; only the per-milestone scope changes.

**Binding scope corrections:**

- **`state/{bronze,silver,gold}.py` are NOT replaced.** `abdp.data.{Bronze,Silver,Gold}Contract` are abstract structural `Protocol[RowT]` types with only `manifest` / `rows`. The local schemas are concrete Pydantic models for the Korean apartment domain (e.g. `BronzeAptTransaction` carries 32 MOLIT fields). They remain younggeul-owned.
- **`storage/snapshot.SnapshotManifest` is NOT replaced.** `abdp.data.SnapshotManifest` is a per-tier UUID-keyed dataclass with parent-pointer lineage; ours is a Pydantic multi-table dataset manifest with sha256-derived `dataset_snapshot_id`. Different concept under the same name. It remains younggeul-owned.
- **`connectors/{retry,manifest,protocol}` adaptation is permanently abandoned** (issue #238 closed). `abdp.core.retry` is a decorator factory with a different invocation contract; `abdp.core.ManifestFactory` produces abdp `SnapshotManifest`, not `BronzeIngestManifest`. Only `connectors/hashing.sha256_payload` was successfully delegated to `abdp.core.stable_hash` (M3, merged).
- **M10 no longer flips the default backend or targets ~600 LOC of deletions.** The success gate becomes "framework logic adopted where semantics actually match, with parity tests covering each adopted surface."

**Revised milestone map (M-prefixes are internal IDs only; not present in issue titles):**

| # | Issue | Revised deliverable |
|---|---|---|
| M4' | [#239](https://github.com/kpubdata-lab/younggeul/issues/239) | `_compat.data` re-exports of `Bronze/Silver/GoldContract`, `SnapshotTier`, `AbdpSnapshotManifest` only. Schemas + storage manifest stay local. |
| M5' | [#242](https://github.com/kpubdata-lab/younggeul/issues/242) | LangGraph run → `abdp.evidence.AuditLog` adapter. |
| M6' | [#243](https://github.com/kpubdata-lab/younggeul/issues/243) | `--render abdp\|legacy` CLI flag using `abdp.reporting.render_{json,markdown}_report`. |
| M7' | [#240](https://github.com/kpubdata-lab/younggeul/issues/240) | Simulation fit-gap matrix + runner-only adapters (no schema replacement). |
| M8' | [#241](https://github.com/kpubdata-lab/younggeul/issues/241) | Expanded parity suite covering every adopted surface. |
| M9' | [#244](https://github.com/kpubdata-lab/younggeul/issues/244) | Shadow-mode `ScenarioRunner` only. LangGraph stays the default execution engine. |
| M10' | [#245](https://github.com/kpubdata-lab/younggeul/issues/245) | Selective-adoption finalization. **No default flip.** Remove only dead shims that selective adoption made unreachable. |

The `YOUNGGEUL_CORE_BACKEND={local,abdp}` flag introduced in M2 still selects between local and adapter-routed code paths where adoption succeeded; the flag's default remains `local` indefinitely.

## References

- Epic: [#235 — Adopt abdp framework for younggeul_core](https://github.com/kpubdata-lab/younggeul/issues/235)
- Upstream: [yeongseon/agent-based-decision-pipeline](https://github.com/yeongseon/agent-based-decision-pipeline)
- Upstream v0.3.0 release: [Auditable Simulation Milestone](https://github.com/yeongseon/agent-based-decision-pipeline/releases/tag/v0.3.0)
- Related: [ADR-002 Monorepo Boundaries](002-monorepo-boundaries.md), [ADR-004 LangGraph Boundaries](004-langgraph-boundaries.md), [ADR-005 Evidence-Gated Reporting](005-evidence-gated-reporting.md)
