# abdp.simulation Fit-Gap Matrix

> **Status**: Build-spec for the shadow-runner work (issue #244) (shadow `ScenarioRunner` + `AuditLog` adapter).
> **Scope of this document**: Per the [ADR-012 selective-adoption scope correction](../adr/012-abdp-backed-core.md#amendment-2026-04-23--selective-adoption-scope-correction) and the LangGraph→AuditLog adapter work (issue #242, deferred and absorbed into #244) deferral re-affirmed by the Oracle consultation on 2026-04-23, this doc is doc-first. It catalogs every surface in `abdp.simulation` against the corresponding surface in `younggeul_core.state.simulation` (and `…/simulation/state.py` graph state) and assigns each gap to a future work item. **No code in `state/simulation.py` is modified by this doc.**

## 1. Scope and non-goals

**In scope**

- Field-level inventory of every public type in `abdp.simulation` and the equivalent (or analogous) surface in younggeul today.
- Per-surface gap classification (`name`, `type`, `semantics`, `missing`, `public-ID-bearing`).
- Per-surface landing decision for the shadow-runner/finalization work (`adapter`, `local-only keep`, `no adoption`).
- Required decision inputs (constraints) for the shadow-runner work to resolve.
- Forbidden patterns and what this doc deliberately does **not** promise.

**Out of scope (deferred to the shadow-runner work in #244 and beyond)**

- Any change to `core/src/younggeul_core/state/simulation.py`.
- Any re-export of `abdp.simulation` Protocols from `_compat`.
- Any "overlap parity" test that would require synthesizing public IDs (`Seed`, `scenario_key`, `snapshot_id`, `proposal_id`, segment IDs).
- Any decision on a concrete ID-generation algorithm (e.g. UUIDv5 in a fixed namespace) — those are shadow-runner design questions and writing them down here would anchor implementation/tests prematurely.
- Any change to LangGraph nodes to record per-step state snapshots.
- Any new public CLI surface (`--seed`, scenario-key flags, etc.).

## 2. Constraints and decision inputs (NOT allocation rules)

This section enumerates the **constraints** that any shadow-runner design must satisfy. It deliberately does **not** prescribe the algorithm.

### Hard constraints (binding)

1. **No public ID synthesis pre-shadow-runner.** Pre-shadow-runner code MUST NOT introduce, persist, expose, or test against any of: `Seed`, `scenario_key`, `snapshot_id` (UUID), `proposal_id`, synthetic segment IDs. These either do not exist in younggeul today or exist in a fundamentally different shape (e.g. sha256 hex vs UUID); inventing them in adapters would encode fake provenance into public surfaces.
2. **`run_id` is identity, not a causal seed.** Deriving any `Seed` value from `run_id` would manufacture false determinism. Any `Seed` introduced by the shadow-runner work must have real cross-engine semantics (e.g. an actual RNG seed used by the simulation), not a re-labelled identity hash.
3. **Default backend stays `local`.** No part of the simulation fit-gap doc, the shadow-runner work, or the selective-adoption finalization may flip the default `YOUNGGEUL_CORE_BACKEND` away from `local`. Adoption is selective and opt-in.
4. **v0.3.0 behavior must remain byte-identical on `local`.** All 1,261 unit tests continue to pass; any new adapter is invoked only on the `abdp` backend.

### Decision inputs the shadow-runner work must resolve (do **not** answer here)

- What semantic role does `Seed` play in younggeul's simulation? (Today the LangGraph nodes have no RNG-seeded behavior; if any randomness is introduced, the seed must be defined as a *first-class* cross-engine concept, not back-ported.)
- What is the public-vs-internal status of synthesized IDs? (The shadow-runner work should default to **internal/opaque/stable** — never surfaced to users — until a user-facing requirement forces otherwise.)
- What is the storage contract for `snapshot_id` if/when it becomes a UUID? (Today's `dataset_snapshot_id` is a sha256 hex digest; any mapping must be reversible/auditable, not a one-way derivation that drops content-addressing.)
- What is the `scenario_key` semantic? (Stable across re-runs of the same scenario? Sensitive to roster/shock changes? The shadow-runner work must define this from the simulation contract, not from the field shape of `ScenarioSpec`.)
- Does `abdp.simulation.SimulationState` (a generic dataclass) need to become the canonical in-memory representation, or can it remain a *projection* of the existing TypedDict `GraphState` produced at the runner boundary?

## 3. Surface inventory matrix

For each `abdp.simulation` symbol, the table records: shape, the analogous younggeul surface, field-level mismatches (tagged), and the shadow-runner/finalization landing.

### 3.1 `ScenarioSpec` — Protocol

| abdp field/method | younggeul (`state.simulation.ScenarioSpec`) | Tag |
|---|---|---|
| `scenario_key: str` (property) | *missing* | `missing`, `public-ID-bearing` |
| `seed: Seed` (property) | *missing* | `missing`, `public-ID-bearing` |
| `build_initial_state(...)` (method) | *missing* (graph state seeded by `seed_graph_state` helper) | `missing`, `semantics` |
| — | `scenario_name: str` | local-only |
| — | `target_gus: tuple[str, ...]` | local-only |
| — | `target_period_start: date` | local-only |
| — | `target_period_end: date` | local-only |
| — | `shocks: tuple[Shock, ...]` | local-only |

**Landing**: `adapter` in the shadow-runner work, wrapping the existing Pydantic model and projecting `scenario_key` + `seed` from shadow-runner-defined sources. **No re-export** until that adapter exists.

### 3.2 `SegmentState` — Protocol

| abdp field | younggeul (`SegmentState`) | Tag |
|---|---|---|
| `segment_id: str` | *missing* (today's `gu_code` is the natural key but is not exposed under that name) | `name`, `missing`, `public-ID-bearing` |
| `participant_ids: tuple[str, ...]` | *missing* (participant↔segment relation is implicit in the round resolver) | `missing`, `semantics` |
| — | `gu_code, gu_name, current_median_price, current_volume, price_trend, sentiment_index, supply_pressure` | local-only |

**Landing**: `adapter` in the shadow-runner work that exposes `gu_code` as `segment_id` and computes `participant_ids` from the runner state. **No re-export** today.

### 3.3 `ParticipantState` — Protocol

| abdp field | younggeul (`ParticipantState`) | Tag |
|---|---|---|
| `participant_id: str` | `participant_id: str` | matches |
| — | `role, capital, holdings, risk_tolerance, sentiment` | local-only |

**Landing**: closest to a true overlap, but adopting the Protocol type in `_compat` is still deferred to the shadow-runner work so the change lands together with the runner-side Protocol conformance for `SegmentState`/`ScenarioSpec`. Adopting it alone would create an asymmetric API surface.

### 3.4 `ActionProposal` — Protocol

| abdp field | younggeul (`ActionProposal`) | Tag |
|---|---|---|
| `proposal_id: str` | *missing* | `missing`, `public-ID-bearing` |
| `actor_id: str` | `agent_id: str` | `name` |
| `action_key: str` | `action_type: Literal[...]` | `name`, `type` |
| `payload: Mapping[str, Any]` | `proposed_value, target_segment, confidence, reasoning_summary, round_no` | `semantics` (younggeul flattens; abdp uses an opaque payload) |

**Landing**: `adapter` in the shadow-runner work that wraps the Pydantic model. The `proposal_id` is a public-ID-bearing field and MUST NOT be synthesized pre-shadow-runner. Renaming `agent_id`→`actor_id` and `action_type`→`action_key` is purely cosmetic on the adapter boundary; the source field names stay.

### 3.5 `SnapshotRef` — concrete dataclass

| abdp field | younggeul (`SnapshotRef`) | Tag |
|---|---|---|
| `snapshot_id: UUID` | `dataset_snapshot_id: str` (sha256 hex) | `name`, `type`, `semantics`, `public-ID-bearing` |
| `tier: SnapshotTier` | *missing* | `missing` |
| `storage_key: str` | *missing* (younggeul resolves snapshots via filesystem path conventions) | `missing` |
| — | `table_count: int` | local-only |
| — | `created_at: datetime` | local-only |

**Landing**: `adapter` in the shadow-runner work. The mapping from sha256 hex to `UUID` is a non-trivial design decision (see §2 — must be reversible/auditable, must not silently drop content-addressing) and is explicitly **deferred** here. This doc does not prescribe a mapping algorithm.

### 3.6 `SimulationState` — generic dataclass

| abdp field | younggeul equivalent | Tag |
|---|---|---|
| `step_index: int` | `round_no: int` (in `GraphState` TypedDict) | `name` |
| `seed: Seed` | *missing* | `missing`, `public-ID-bearing` |
| `snapshot_ref: SnapshotRef` | `SnapshotRef` (in `GraphState`, sha256-based; see §3.5) | `type`, `semantics`, `public-ID-bearing` |
| `segments: tuple[S, ...]` | computed from snapshot reader; not stored as a single tuple in `GraphState` | `semantics` |
| `participants: tuple[P, ...]` | `participant_roster` in `GraphState` | `name`, `semantics` |
| `pending_actions: tuple[A, ...]` | `pending_proposals` in `GraphState` | `name` |

**Landing**: `adapter` in the shadow-runner work that **projects** the existing `GraphState` TypedDict into an `abdp.simulation.SimulationState` snapshot at the runner boundary. The `GraphState` TypedDict remains the canonical in-memory representation; this doc does **not** propose making `SimulationState` canonical.

### 3.7 younggeul-only types (no abdp counterpart)

`RunMeta`, `RoundOutcome`, `ReportClaim`, `Shock` — these encode younggeul-specific simulation semantics (Korean apartment market, evidence-gated reporting, shock parameterization). **Landing**: `local-only keep` permanently; out of scope for any abdp adoption.

## 4. Per-surface migration plan

| Surface | Work item | Adapter shape | Validating test (do **not** add until the work item) |
|---|---|---|---|
| `ScenarioSpec` | the shadow-runner work | wrap `ScenarioSpec` Pydantic model; project `scenario_key` and `seed` from shadow-runner-defined sources | Protocol-conformance test against `abdp.simulation.ScenarioSpec` |
| `SegmentState` | the shadow-runner work | wrap; expose `gu_code` as `segment_id`; compute `participant_ids` from runner state | Protocol-conformance test |
| `ParticipantState` | the shadow-runner work (with `ScenarioSpec`/`SegmentState`) | wrap; trivial field mapping | Protocol-conformance test |
| `ActionProposal` | the shadow-runner work | wrap; project `proposal_id` from shadow-runner-defined source; rename `agent_id`→`actor_id`, `action_type`→`action_key`; flatten remainder into `payload` | Protocol-conformance test + round-trip adapter test |
| `SnapshotRef` | the shadow-runner work | wrap; map sha256 hex → `UUID` per the shadow-runner design (reversible/auditable, see §2); supply `tier` and `storage_key` from existing path conventions | Adapter test + reversibility test |
| `SimulationState` | the shadow-runner work | runner-boundary projection from `GraphState` TypedDict | Snapshot-projection test |
| `AuditLog` | the shadow-runner work (absorbed from #242) | shadow `ScenarioRunner` records `ScenarioStep` snapshots; full `AuditLog.__post_init__` invariants hold | Round-trip + invariant test (see #244) |
| `RunMeta`, `RoundOutcome`, `ReportClaim`, `Shock` | (none) | — | — |
| Default backend flip | the selective-adoption finalization | none — confirm no flip happens | guardrail test |

## 5. Forbidden patterns (fit-gap doc through parity-suite expansion)

These are **binding** for any work landed before the shadow-runner work opens:

- ✗ Do not introduce `Seed` anywhere — not as a field, not as a CLI flag, not as a derived value, not as a parameter to internal helpers.
- ✗ Do not synthesize `scenario_key`, `snapshot_id` (UUID), `proposal_id`, or segment IDs in any code path that survives `_compat` boundaries.
- ✗ Do not re-export `abdp.simulation.{ScenarioSpec, SegmentState, ParticipantState, ActionProposal, SnapshotRef, SimulationState}` from `younggeul_core._compat`.
- ✗ Do not write parity tests that compare today's Pydantic models to abdp Protocols at the field level. They do not overlap in the way a parity test would assert; the test would either fail or be made to pass by inventing forbidden values.
- ✗ Do not describe today's local fields as "equivalent" to abdp counterparts in user-facing docs where the relationship is only loosely analogous (see the `name`/`type`/`semantics` tags above).
- ✗ Do not promise cross-engine determinism, schema parity, or stable public IDs in this milestone.
- ✗ Do not modify LangGraph nodes to record per-step `SimulationState` snapshots. That is the shadow-runner work.

## 6. Required shadow-runner design decisions (open questions) — RESOLVED

> **Status (2026-04-23): Resolved by Oracle's binding design ruling for the shadow-runner work and shipped in PR #254 (ID helpers), PR #255 (scenario adapter), and PR #256 (shadow runner).** Each open question's resolution is recorded inline below.

The shadow-runner work must resolve the following before it can build the adapters in §4. This doc does **not** answer them:

1. What is the canonical source of `Seed`? (See §2 hard constraints — must be a real RNG seed with cross-engine semantics, not derived from `run_id`.) — **RESOLVED**: `Seed: int = 0` runner-internal default (`DEFAULT_SHADOW_SEED` in `younggeul_core._compat.ids`). No CLI flag introduced. The seed is fixed because the shadow runner exercises deterministic policies whose decisions don't consume RNG.
2. What is the canonical source of `scenario_key`? — **RESOLVED**: `yg-scenario-v1:<full sha256 hex>` of the canonicalized `ScenarioSpec` JSON (see `derive_scenario_key`). Hash is never truncated.
3. What is the mapping algorithm for `snapshot_id` (sha256 hex → UUID)? — **RESOLVED**: `uuid5(YOUNGGEUL_SNAPSHOT_NAMESPACE, sha256_hex)` with a per-run `SnapshotIdRegistry` that records the bijection so the original sha256 is never lost.
4. What is the public-vs-internal status of synthesized IDs? — **RESOLVED**: All synthesized IDs (Seed, scenario_key, snapshot UUID, proposal_id) are runner-internal. They appear only in the abdp `AuditLog` JSON written under `--shadow-audit-log`; they MUST NOT appear in markdown reports, CLI summary text, or younggeul-owned PK storage. The shadow audit-log integration test asserts the markdown report does not contain `yg-scenario-v1:`.
5. Does `SimulationState` become the canonical in-memory form, or remain a runner-boundary projection? — **RESOLVED**: Projection-only. The LangGraph `GraphState` TypedDict (in `apps/`) remains canonical; `SimulationState` (in `core`) and abdp's `SimulationState` are runner-boundary projections built by `to_abdp_simulation_state`.

## 7. Verification

This fit-gap doc is doc-only and has **no code change**. Verification is:

- This file exists at `docs/architecture/abdp-simulation-fit-gap.md`.
- Issue #240 description is updated to point here and reflect the doc-only scope.
- Issue #244 references this doc as its build-spec input.
- ADR-012 amendment table reflects the simulation fit-gap doc as `doc-only`.

No new tests are added. The 1,261-pass unit suite remains untouched.

## 8. Cross-references

- [ADR-012: abdp-backed core compatibility architecture](../adr/012-abdp-backed-core.md)
- Epic [#235](https://github.com/kpubdata-lab/younggeul/issues/235)
- Simulation fit-gap doc issue [#240](https://github.com/kpubdata-lab/younggeul/issues/240)
- Shadow-runner issue [#244](https://github.com/kpubdata-lab/younggeul/issues/244) (consumes this doc)
- Deferred issue [#242](https://github.com/kpubdata-lab/younggeul/issues/242) (absorbed into #244 per the 2026-04-23 Oracle ruling)
