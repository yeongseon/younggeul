# ADR-011: Wire live snapshot data into the simulate CLI

## Status
Accepted

## Date
2026-04-21

## Context

The `simulate` LangGraph pipeline already had a typed live path inside `world_initializer`, `scenario_builder`, and `participant_decider`, designed to consume snapshot-derived market state instead of fixture constants. That live path was effectively unreachable from the CLI:

- `cli.py:simulate_command` constructed the graph via `build_simulation_graph(event_store, evidence_store=...)` with no snapshot reader injected, so the runtime always fell into the fixture stub branch.
- The stub branches in `world_initializer` and `scenario_builder` hard-coded Gangnam (`gu_code="11680"`), `target_gus=["11680"]`, `median_price=2_000_000`, and `volume=100`. These values exist to keep the demo and unit tests deterministic, but they bear no resemblance to real MOLIT trade data.
- A `SnapshotReader` Protocol existed in `simulation/ports/snapshot_reader.py`, but no concrete implementation read the snapshot directory layout produced by `younggeul snapshot publish` and the baseline forecasts produced by `younggeul baseline`.

Operationally this meant every `younggeul simulate` invocation — including ones run immediately after a successful 25-구 live ingest, snapshot, and baseline pipeline — produced a report whose headline number was the 2,000,000 KRW stub. The simulation could not surface real prices even when real prices were sitting in the snapshot directory next to it.

ADR-003 (immutable snapshots), ADR-005 (evidence-gated reporting), and ADR-007 / ADR-008 (live ingest) all assume that the simulation consumes the artifacts the data plane produces. Without a concrete snapshot reader and a CLI surface to opt into it, that contract was only honored on paper.

## Decision

The `simulate` CLI now accepts an opt-in snapshot directory and threads the live snapshot, scenario, and participant roster through `seed_graph_state` into the LangGraph execution. The fixture stub remains the default for `simulate` invocations that do not pass `--snapshot-dir`, so demos, unit tests, and the `--source=fixture` ingest path continue to work unchanged.

### 1. Concrete snapshot reader

`apps/kr-seoul-apartment/src/younggeul_app_kr_seoul_apartment/simulation/adapters/filesystem_snapshot_reader.py` implements the `SnapshotReader` protocol against the on-disk layout `younggeul snapshot publish` and `younggeul baseline` already produce:

- it discovers the latest snapshot directory and verifies its SHA-256,
- it loads the gold market slices for the requested gu codes,
- it loads the matching baseline forecast records when a baseline directory is provided,
- it returns typed `SnapshotRef`, `ScenarioSpec`, and `ParticipantRoster` values that the graph nodes already know how to consume.

This adapter lives in `simulation/adapters/` rather than `simulation/ports/` to preserve the ports/adapters separation: the protocol stays infrastructure-free, the filesystem implementation depends on the protocol.

### 2. Opt-in CLI surface

`younggeul simulate` gains three new options:

- `--snapshot-dir <path>` — the directory that contains published snapshots,
- `--baseline-dir <path>` — the directory that contains baseline forecast outputs,
- `--gus <csv>` — the 5-digit MOLIT sigungu codes to materialize into the simulation.

When `--snapshot-dir` is omitted, the CLI behaves exactly as before. When it is provided, the CLI constructs a `FilesystemSnapshotReader`, asks it for the snapshot/scenario/roster triple, and passes those into `seed_graph_state` before running the graph. There is no implicit auto-discovery of snapshot directories, because silent fallback to whatever happens to be on disk would weaken the SHA-256 reproducibility guarantee from ADR-003.

### 3. Stubs preserve seeded state when present

`world_initializer`, `scenario_builder`, and `participant_decider` continue to expose their fixture stubs, but each stub now early-returns the seeded value if `seed_graph_state` populated it. This keeps two properties simultaneously:

- the fixture demo and the existing test suite, which rely on the stubs, are not destabilized,
- the live path is now the source of truth whenever the CLI seeds state from a snapshot.

`seed_graph_state` accepts optional `snapshot`, `scenario`, and `participant_roster` keyword arguments that default to `None`, so existing call sites compile and behave identically.

### 4. Tests

- `tests/unit/test_filesystem_snapshot_reader.py` exercises the adapter against on-disk fixture snapshots, including the SHA-256 verification path.
- `tests/unit/test_graph.py` adds coverage for the seeded-state preservation behavior in the stub branches.
- `tests/integration/test_simulate_cli_with_snapshot.py` runs the full `younggeul simulate --snapshot-dir ...` invocation end-to-end.

The full suite is `1241 passed, 6 skipped, 3 deselected`, up from 1233 prior to this change.

## Alternatives Considered

### A) Replace the stub branches with the live path unconditionally

- **Pros**
  - One canonical code path; nothing to forget to wire.
  - Eliminates the risk of shipping a stub-derived report by accident.
- **Cons**
  - Breaks `make demo` and many unit tests that depend on the deterministic stub.
  - Forces every contributor to materialize a snapshot before running the simulator, which is a non-trivial onboarding regression.
  - Tightly couples the simulation graph to filesystem I/O, blocking in-memory variants used by tests.

### B) Auto-discover the most recent snapshot directory inside the CLI

- **Pros**
  - Zero-config "live" runs after an ingest pipeline.
- **Cons**
  - Implicit behavior is hostile to ADR-003's SHA-256 reproducibility model: the same `younggeul simulate` command would produce different outputs depending on filesystem mtime.
  - Hides snapshot selection from CI logs and report metadata, weakening evidence traceability under ADR-005.

### C) Inject the snapshot reader through environment variables instead of CLI flags

- **Pros**
  - Smaller CLI surface.
- **Cons**
  - Environment-driven configuration is invisible in logs and harder to grep for after the fact.
  - Inconsistent with the rest of the CLI, which uses explicit options for filesystem inputs.

The chosen design picks an explicit, opt-in CLI option and a typed `SnapshotReader` adapter because both align with the existing evidence-gated, deterministic-pipeline posture of the project.

## Consequences

**Pros.**

- `younggeul simulate --snapshot-dir <dir>` produces reports keyed to real MOLIT-derived prices. End-to-end verification on snapshot `9bdcc5f1...` produced a Gangnam median of 2,581,369,914 KRW with volume 74, in place of the previous 2,000,000 KRW / volume 100 stub.
- The data plane → simulation plane contract assumed by ADR-003, ADR-005, ADR-007, and ADR-008 is now honored at the CLI surface, not just inside the graph.
- The `SnapshotReader` Protocol now has a reference implementation, so future readers (e.g. cloud object stores, in-memory test doubles) have a documented shape to match.

**Cons.**

- Two visible code paths (stub vs. live) remain inside the graph nodes. They must be kept in sync; an inadvertent change to a stub field that has no live counterpart could create silent drift.
- Live runs depend on the snapshot directory being well-formed and SHA-256 verifiable. Misplaced or partially written snapshots will surface as adapter-level errors rather than as graph-level failures.
- The CLI now has more surface area, which means slightly more documentation maintenance and more parameter combinations to consider when reasoning about reproducibility.

## Related

- [ADR-003: Immutable Dataset Snapshots](003-immutable-dataset-snapshots.md)
- [ADR-004: LangGraph Usage Boundaries](004-langgraph-boundaries.md)
- [ADR-005: Evidence-Gated Reporting](005-evidence-gated-reporting.md)
- [ADR-007: Live Ingest via kpubdata](007-kpubdata-live-ingest.md)
- [ADR-010: Run live ingest from the GitHub Actions data pipeline workflow](010-data-pipeline-live-workflow.md)
- `apps/kr-seoul-apartment/src/younggeul_app_kr_seoul_apartment/simulation/adapters/filesystem_snapshot_reader.py`
- `apps/kr-seoul-apartment/src/younggeul_app_kr_seoul_apartment/simulation/ports/snapshot_reader.py`
- `apps/kr-seoul-apartment/src/younggeul_app_kr_seoul_apartment/cli.py` — `simulate_command`
