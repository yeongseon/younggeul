# Data Pipeline

The Younggeul data pipeline is a three-layer ETL process that transforms raw government API responses into aggregated market metrics.

## Architecture

```
Data Sources           Bronze Layer       Silver Layer          Gold Layer
(MOLIT, BOK,    →→→   (Raw JSON/CSV)  →  (Typed Pydantic)  →  (Aggregated)
 KOSTAT)               per-source         per-domain            per gu/month
```

---

## Bronze Layer

The Bronze layer stores **raw, unmodified** API responses from official sources.

| Source | Data Type | Description |
|--------|-----------|-------------|
| **MOLIT** | Apartment transactions | Real estate transaction prices from Ministry of Land |
| **BOK** | Interest rates | Bank of Korea base rate time series |
| **KOSTAT** | Migration data | Population migration between districts |

Bronze records are written as-is — no transformation, no filtering. This ensures the raw source is always available for audit.

---

## Silver Layer

The Silver layer converts Bronze records into **typed Pydantic models** with validated fields.

| Model | Source | Key Fields |
|-------|--------|------------|
| `SilverAptTransaction` | MOLIT | district, year_month, area_m2, price_krw |
| `SilverInterestRate` | BOK | date, rate_pct |
| `SilverMigration` | KOSTAT | origin_gu, dest_gu, year_month, count |

Each Silver record carries `source_id` and `source_url` metadata for citation tracking.

---

## Gold Layer

The Gold layer produces **aggregated district-level monthly metrics**.

| Model | Granularity | Key Fields |
|-------|-------------|------------|
| `GoldDistrictMonthlyMetrics` | gu × month | avg_price_krw, median_price_krw, transaction_count, yoy_pct, mom_pct |

Gold records are the primary input to the simulation plane.

### Trend Enrichment

Gold metrics include YoY (year-over-year) and MoM (month-over-month) percentage changes calculated during aggregation.

---

## Snapshot System

Snapshots provide **immutable, reproducible** pipeline outputs.

```bash
younggeul snapshot publish --data-dir ./output/pipeline --snapshot-dir ./output/snapshots
```

Each snapshot:
- Has a unique ID (`snap_YYYYMMDD_<hash8>`)
- Contains a `manifest.json` with SHA-256 hashes for all files
- Is verified on load — any tampered file raises `SnapshotIntegrityError`

```bash
younggeul snapshot list --snapshot-dir ./output/snapshots
```

---

## Baseline Forecaster

The baseline module produces a simple **statistical forecast** from the latest Gold metrics, used as a starting point for simulation scenarios.

```bash
younggeul baseline --snapshot-dir ./output/snapshots --output-dir ./output/baseline
```

The baseline is a deterministic computation — given the same snapshot, it always produces the same output.
