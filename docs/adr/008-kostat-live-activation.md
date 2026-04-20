# ADR-008: Activate KOSTAT Migration in Live Ingest at 시도 Granularity

## Status
Accepted

## Date
2026-04-20

## Context

[ADR-007 §5](007-kpubdata-live-ingest.md) deliberately excluded KOSTAT population migration from live mode at v0.1 launch on the grounds that the kpubdata `kosis.population_migration` dataset (KOSIS table `DT_1B26003_A01`, 시도별 이동자수) appeared to expose only the aggregate metrics `T70`/`T80` and could not populate the per-region `in_count`/`out_count`/`net_count` fields of `BronzeMigration`.

Subsequent investigation showed two facts that invalidate that reasoning:

1. **Matrix collapse is sufficient.** `DT_1B26003_A01` is an origin (`C1`) × destination (`C2`) × metric matrix. The `'00'` (전국) sentinel on either axis already yields per-region totals — `(C1='00', C2=region)` is total inflow into `region`, and `(C1=region, C2='00')` is total outflow. We do not need a different KOSIS table to fill the Bronze schema; collapsing the existing matrix on the 전국 axis is enough.
2. **The 시도 → 시군구 join is free.** `transforms.gold_district._find_net_migration` already keys on `gu_code[:2]`, which equals the 2-digit KOSIS 시도 code (e.g. `11680[:2] == '11' == 서울특별시`). 시도-level migration rows therefore propagate to every Seoul gu without any external mapping table or Bronze schema change.

The `kpubdata` library does **not** expose a 시군구-level migration table (`DT_1B26001_A01`). Reaching that granularity would require a direct KOSIS Open API HTTP client. We chose to stay within kpubdata for v0.1 to preserve the "single client library" invariant from ADR-007 §1.

## Decision

KOSTAT population migration is wired into live ingest at **시도 (province) granularity** via the kpubdata `kosis.population_migration` dataset. Specifically:

1. **Connector contract.** `KostatMigrationConnector.fetch(KostatMigrationRequest(year_month=YYYYMM))` returns one `BronzeMigration` per non-aggregate destination province present in the response. The pivot rules are:

   | Bronze field | Source rows |
   |---|---|
   | `in_count`  | `T70` where `C1 == '00'` and `C2 == region` |
   | `out_count` | `T70` where `C1 == region` and `C2 == '00'` |
   | `net_count` | `T80` where `C1 == '00'` and `C2 == region` |

   `region_code` is the 2-digit KOSIS code (e.g. `'11'` for Seoul). Self-loops (`C1 == C2`) and inter-region pairs are skipped — they would double-count flows once collapsed.

2. **Pipeline wiring.** `pipeline_live.run_live_ingest_gus_months` issues exactly **one KOSIS call per month** (region scope is implicit — every 시도 comes back in one response). MOLIT and BOK fan-out is unchanged.

3. **Auth and rate limiting.** The connector reuses the existing `kpubdata.Client` constructed by `connectors.client_factory.build_client` (which already validates `KPUBDATA_KOSIS_API_KEY`). The shared `RateLimiter(min_interval=1.0)` from `pipeline_live` covers KOSIS calls alongside MOLIT and BOK.

4. **Failure semantics.** A failed KOSIS call records a `failed` manifest and returns zero records — the pipeline still emits Gold rows with `net_migration = None`. Duplicate metrics for the same `(region, period)` raise `NonRetryableError` because that signals a malformed response.

## Consequences

**Pros.**

- `GoldDistrictMonthlyMetrics.net_migration` is now populated in live mode — verified end-to-end with `younggeul ingest --source live --gu 11680 --month 202503` returning `net_migration=1306` for 강남구 March 2025 (matches the KOSIS Seoul-wide net inflow, 110,859 in − 109,553 out).
- The `migrations: []` placeholder in `BronzeInput` is gone, so Silver normalizers and Gold aggregators exercise the same code path live and on fixtures.
- No new dependencies; no Bronze schema change; no mapping table.

**Cons.**

- All Seoul gus share the same `net_migration` value within a given month (Seoul-wide net inflow), which limits cross-gu comparability for migration-driven simulation signals. We accept this for v0.1 and revisit if/when the multi-region scope from ADR-007 §7 expands beyond Seoul.
- The connector silently skips inter-region rows; a future requirement to surface origin → destination flows would need a different pivot.

## Alternatives Considered

- **Direct KOSIS Open API for `DT_1B26001_A01`** (시군구별 이동자수). Would give per-gu migration but breaks ADR-007's single-client-library invariant and adds an httpx dependency to the connector layer. Reconsider when v0.1 scope expands beyond Seoul.
- **Bronze schema change.** Adding `gross_inflow`/`gross_outflow` columns matching kpubdata's native shape. Rejected because it would invalidate existing Silver normalizers, fixtures, and snapshot hashes for no Gold-level benefit at this granularity.
- **Stay on option C (omit KOSTAT).** Rejected because the gross_in/gross_out matrix collapse trivially satisfies the existing schema once the axis semantics are documented.

## Related

- [ADR-007: Live Ingest via kpubdata](007-kpubdata-live-ingest.md) — superseded §5.
- `apps/kr-seoul-apartment/src/younggeul_app_kr_seoul_apartment/connectors/kostat.py` — implementation.
- `apps/kr-seoul-apartment/tests/unit/test_kostat.py` — pivot-axis fixtures.
