# Data Plane

The data plane is a three-layer ETL pipeline that transforms raw Korean government API data into structured market metrics.

## Layer Summary

```
MOLIT ──┐
BOK  ───┼──► Bronze ──► Silver ──► Gold ──► Snapshot
KOSTAT ─┘    (raw)     (typed)   (agg.)    (immutable)
```

---

## Bronze Layer — Raw Connectors

Each connector implements the `BronzeConnector` protocol:

```python
class BronzeConnector(Protocol):
    def fetch(self, **kwargs) -> list[BronzeRecord]: ...
```

| Connector | Source | Record Type |
|-----------|--------|-------------|
| `MolitConnector` | MOLIT open API | `BronzeAptTransaction` |
| `BokConnector` | BOK statistics API | `BronzeInterestRate` |
| `KostatConnector` | KOSTAT migration data | `BronzeMigration` |

Bronze records are stored as JSON with `raw_payload` preserving the original response.

---

## Silver Layer — Typed Models

Silver models are Pydantic v2 models with strict validation:

```
BronzeAptTransaction  →  SilverAptTransaction
BronzeInterestRate    →  SilverInterestRate
BronzeMigration       →  SilverMigration
```

All Silver models include:

- `source_id: str` — connector identifier
- `source_url: str` — canonical URL for citation
- `fetched_at: datetime` — ingestion timestamp

---

## Gold Layer — Aggregated Metrics

Gold aggregates Silver records to `(gu, year_month)` granularity:

```
GoldDistrictMonthlyMetrics
├── gu: str                     # District code (e.g., "11680")
├── year_month: str             # "YYYY-MM"
├── avg_price_krw: float
├── median_price_krw: float
├── transaction_count: int
├── yoy_pct: float | None       # Year-over-year change
└── mom_pct: float | None       # Month-over-month change
```

### Trend Enrichment

YoY and MoM values are computed during Gold aggregation by joining current and prior-period records.

---

## Pipeline Composition

```python
from younggeul_app_kr_seoul_apartment.pipeline import run_pipeline

result = run_pipeline(output_dir=Path("./output/pipeline"))
```

`run_pipeline()` orchestrates Bronze → Silver → Gold in sequence and writes output to disk.

---

## Snapshot System

### Publishing

```python
from younggeul_core.storage import publish_snapshot

manifest = publish_snapshot(
    data_dir=Path("./output/pipeline"),
    snapshot_dir=Path("./output/snapshots"),
)
```

### Resolving

```python
from younggeul_core.storage import resolve_snapshot

snapshot = resolve_snapshot(
    snapshot_dir=Path("./output/snapshots"),
    snapshot_id="snap_20260101_abc123",   # or None for latest
)
```

Snapshots are verified on load — `SnapshotIntegrityError` is raised if any file hash mismatches.

---

## Baseline Forecaster

A simple statistical model that produces a `BaselineForecast` from the latest Gold metrics:

```python
from younggeul_app_kr_seoul_apartment.pipeline import generate_baseline

forecast = generate_baseline(snapshot=snapshot)
```

The baseline is deterministic: same snapshot → same forecast, always.
