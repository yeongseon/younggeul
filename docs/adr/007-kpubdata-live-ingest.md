# ADR-007: Live Ingest via kpubdata

## Status
Accepted

## Date
2026-04-19

## Context
Until v0.1, the `younggeul ingest` command only operated on hand-crafted fixture data. The pipeline (Bronze → Silver → Gold) was wired and validated end-to-end, but no path existed for users to fetch real Seoul apartment trades, BOK base rates, or KOSTAT migration data from the upstream public APIs.

We previously evaluated using [PublicDataReader](https://github.com/WooilJeong/PublicDataReader) directly inside the connector layer, but doing so couples our code to a single library's interface and forces us to re-implement provider-specific error handling, rate limiting, and envelope parsing for every connector.

[`kpubdata`](https://pypi.org/project/kpubdata/) is a sister project that provides a unified `Client` over the same public data sources (data.go.kr / 국토교통부 RTMS, BOK ECOS, KOSIS). It already encapsulates:
- Provider auth (`Client.from_env()` reads `KPUBDATA_*_API_KEY`).
- Envelope/response shape normalization across MOLIT family endpoints.
- Dataset-level access via `client.dataset("datago.apt_trade")` style handles.

Using kpubdata removes per-connector boilerplate while keeping our pipeline deterministic and replayable.

## Decision
The live ingest path will use **kpubdata as the single client library** for all three providers.

1. **Pinned dependency**: `kpubdata>=0.2.3` in `pyproject.toml`. The 0.2.3 release is the first that correctly handles the `resultCode == "000"` envelope returned by MOLIT's RTMS family endpoints (PR #130 in kpubdata).
2. **Single client factory**: `younggeul_app_kr_seoul_apartment.connectors.client_factory.build_client()` is the only place that constructs a `kpubdata.Client`. It validates that `KPUBDATA_DATAGO_API_KEY`, `KPUBDATA_BOK_API_KEY`, and `KPUBDATA_KOSIS_API_KEY` are all present and raises a single actionable error message otherwise.
3. **Live ingest entry point**: `pipeline_live.run_live_ingest(client, lawd_code, deal_ym)` fetches one Seoul `gu × month` slice and returns a `BronzeInput` ready for `run_pipeline`.
4. **CLI surface**: `younggeul ingest --source live --gu <5-digit LAWD>` with either `--month <YYYYMM>` (single month) or `--months <YYYYMM,YYYYMM,...>` (multi-month, mutually exclusive). Multi-month invocations issue one MOLIT call per month and a single BOK range query, then concatenate into one `BronzeInput` so the aggregator can populate YoY/MoM change ratios. The default `--source=fixture` path is unchanged so `make demo` keeps working without API keys.
5. **KOSTAT scope (option C)**: For v0.1, KOSTAT migration is **not emitted** in live mode (`BronzeInput.migrations` is an empty list). The kpubdata `kosis.population_migration` dataset only exposes `T70` (이동자수) and `T80` (순이동자수), while our `BronzeMigration` schema requires per-region in/out/net counts. Wiring real KOSTAT migration requires either a different KOSIS table or a Bronze schema change, which is tracked separately. The Silver normalizer drops migration rows with all-null counts anyway, so emitting a placeholder Bronze row would be dead code.
6. **Live integration test**: One gated test (`apps/kr-seoul-apartment/tests/integration/test_live_ingest.py`) exercises the full live path under the `live` pytest marker. It is excluded from `make test` and `make test-all`, and skipped when env vars are absent.

## Alternatives Considered
### A) Use PublicDataReader directly per connector
- **Pros**: Mature library, well-known in the Korean public data community.
- **Cons**: Each connector re-implements auth, envelope parsing, and error normalization. Migrating between providers (e.g., a future Naver/KB-style connector) would require duplicating the same scaffolding again.

### B) Hand-rolled httpx clients per provider
- **Pros**: Zero third-party surface; full control.
- **Cons**: We would re-derive every provider's quirks ourselves (e.g., MOLIT's `resultCode == "000"` vs `"00"` discrepancy that kpubdata 0.2.3 fixes). High maintenance load for no architectural gain.

### C) kpubdata as the unified client (Selected)
- **Pros**: One auth surface, one envelope handler, one place to fix provider-side bugs upstream. Aligns with the project's "deterministic data plane, no LLMs" principle.
- **Cons**: Adds an upstream dependency; we have to ship a kpubdata release whenever a provider-side issue is discovered (e.g., the 0.2.3 release blocking this work).

## Rationale
Option C concentrates provider-coupling complexity in one place — the kpubdata library — and lets the younggeul connectors stay thin adapters that translate kpubdata responses into our typed Bronze schemas. When MOLIT changed its envelope format, the fix was a one-line patch in kpubdata + a version bump here, not a sweep across every connector.

The KOSTAT decision (option C in §5) is a deliberate v0.1 trade-off: we keep `BronzeInput` shape stable but emit zero migration rows, rather than fabricating in/out/net values we cannot derive from the available KOSIS metric set or shipping a Bronze placeholder that the Silver normalizer would drop anyway.

## Examples
### 1) Building a client and running a live ingest

```python
from younggeul_app_kr_seoul_apartment.connectors.client_factory import build_client
from younggeul_app_kr_seoul_apartment.pipeline_live import run_live_ingest
from younggeul_app_kr_seoul_apartment.pipeline import run_pipeline

client = build_client()
bronze = run_live_ingest(client=client, lawd_code="11680", deal_ym="202503")
result = run_pipeline(bronze)
```

### 2) CLI usage

```bash
set -a; source .env; set +a

# Single month
younggeul ingest --source live --gu 11680 --month 202503 --output-dir ./output/live

# Year-over-year (populates yoy_*_change in Gold)
younggeul ingest --source live --gu 11680 --months 202403,202503 --output-dir ./output/live-yoy

# Month-over-month (populates mom_*_change in Gold)
younggeul ingest --source live --gu 11680 --months 202502,202503 --output-dir ./output/live-mom
```

The default fixture path remains:

```bash
younggeul ingest --output-dir ./output/pipeline
```

### 3) Required environment variables

```bash
export KPUBDATA_DATAGO_API_KEY=...   # data.go.kr (MOLIT RTMS)
export KPUBDATA_BOK_API_KEY=...      # 한국은행 ECOS
export KPUBDATA_KOSIS_API_KEY=...    # 통계청 KOSIS
```

## Consequences
### Positive
- **One bug-fix surface**: Provider quirks live in kpubdata and propagate to younggeul via a version bump.
- **Demo unchanged**: `make demo` and `--source=fixture` keep working with no API keys, preserving onboarding ergonomics from ADR-006.
- **Gated live test**: `make test` and `make test-all` never hit external APIs by accident; the `live` marker is opt-in.

### Negative
- **Upstream coupling**: Bug fixes for provider-side changes block on a kpubdata release.
- **KOSTAT gap**: Live migration data is unavailable in v0.1 (`BronzeInput.migrations == []`). Downstream consumers see `null` for `net_migration` in Gold output until a follow-up ADR resolves the KOSIS metric mapping.

### Neutral
- **Connector tests stay synthetic**: Per ADR-006, unit tests still mock the kpubdata dataset interface; only the gated live test hits real endpoints.

## References
- ADR-003: Immutable Dataset Snapshots
- ADR-006: Public Data Publication Policy
- kpubdata PR #130 (MOLIT envelope fix; released as 0.2.3)
