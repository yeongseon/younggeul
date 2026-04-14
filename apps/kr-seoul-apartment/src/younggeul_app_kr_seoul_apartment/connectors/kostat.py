"""KOSTAT population migration connector using kpubdata KOSIS API."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, ClassVar

import pandas as pd
from kpubdata.core.dataset import Dataset

from younggeul_core.connectors.hashing import sha256_payload
from younggeul_core.connectors.manifest import build_manifest
from younggeul_core.connectors.protocol import ConnectorResult
from younggeul_core.connectors.rate_limit import RateLimiter
from younggeul_core.connectors.retry import NonRetryableError, retry
from younggeul_core.state.bronze import BronzeMigration

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Required columns from the KOSIS StatisticSearch (통계자료) response.
REQUIRED_COLUMNS: frozenset[str] = frozenset(
    {
        "C1",
        "C1_NM",
        "ITM_ID",
        "ITM_NM",
        "PRD_DE",
        "DT",
    }
)

# Metric item codes → BronzeMigration field mapping
METRIC_MAP: dict[str, str] = {
    "T20": "in_count",  # 전입
    "T25": "out_count",  # 전출
    "T30": "net_count",  # 순이동
}

# Sentinel codes that represent aggregate/total rows in the C2 dimension.
# We filter to these to get region-level summaries (not origin-destination pairs).
_TOTAL_SENTINELS: frozenset[str] = frozenset({"00", "ALL", ""})


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True, slots=True)
class KostatMigrationRequest:
    """Partition-scoped request for one month of migration data.

    Attributes:
        year_month: Period in YYYYMM format (e.g., "202301").
        org_id: KOSIS organization ID (default "101" for 통계청).
        tbl_id: KOSIS table ID (default "DT_1B26003_A01" for 시도별 이동자수).
    """

    year_month: str
    org_id: str = "101"
    tbl_id: str = "DT_1B26003_A01"


def _safe_str(value: object) -> str | None:
    """Convert a pandas cell value to str | None.

    - NaN / None → None
    - Whitespace-only → None
    - everything else → str(value), stripped
    """
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or pd.isna(value)):
        return None
    result = str(value).strip()
    return result if result else None


def _filter_aggregate_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Filter to aggregate rows where C2 is a total sentinel.

    This keeps one-region summaries rather than origin-destination pairs.
    """
    if "C2" not in df.columns:
        # Table has no C2 dimension — treat all rows as aggregate
        return df
    return df[df["C2"].astype(str).str.strip().isin(_TOTAL_SENTINELS)].copy()


def _filter_target_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only rows for metrics we care about (T20, T25, T30)."""
    return df[df["ITM_ID"].astype(str).str.strip().isin(METRIC_MAP)].copy()


def _pivot_to_region_rows(
    df: pd.DataFrame,
) -> list[dict[str, Any]]:
    """Pivot long-format KOSIS rows to one dict per (region, period).

    Input: long rows with (C1, C1_NM, PRD_DE, ITM_ID, DT)
    Output: pivoted dicts with (region_code, region_name, year, month, in_count, out_count, net_count)

    Raises NonRetryableError if duplicate metrics found for any (region, period).
    """
    groups: dict[tuple[str, str, str], dict[str, Any]] = {}

    for _, row in df.iterrows():
        region_code = _safe_str(row.get("C1"))
        region_name = _safe_str(row.get("C1_NM"))
        prd_de = _safe_str(row.get("PRD_DE"))
        itm_id = _safe_str(row.get("ITM_ID"))
        value = _safe_str(row.get("DT"))

        if not region_code or not prd_de or not itm_id:
            continue

        key = (region_code, region_name or "", prd_de)
        bronze_field = METRIC_MAP.get(itm_id)
        if bronze_field is None:
            continue

        if key not in groups:
            year = prd_de[:4] if len(prd_de) >= 4 else prd_de  # noqa: PLR2004
            month = prd_de[4:6] if len(prd_de) >= 6 else None  # noqa: PLR2004
            groups[key] = {
                "region_code": region_code,
                "region_name": region_name,
                "year": year,
                "month": month,
                "in_count": None,
                "out_count": None,
                "net_count": None,
            }

        if groups[key].get(bronze_field) is not None:
            msg = f"Duplicate metric {itm_id} for region={region_code} period={prd_de}"
            raise NonRetryableError(msg)

        groups[key][bronze_field] = value

    # Deterministic ordering: sort by (region_code, year, month)
    return [groups[k] for k in sorted(groups.keys())]


def _map_to_bronze(
    pivoted_rows: list[dict[str, Any]],
    *,
    source_id: str,
    ingest_timestamp: datetime,
    raw_response_hash: str,
) -> list[BronzeMigration]:
    """Map pivoted normalized dicts to BronzeMigration records."""
    records: list[BronzeMigration] = []
    for row in pivoted_rows:
        records.append(
            BronzeMigration(
                ingest_timestamp=ingest_timestamp,
                source_id=source_id,
                raw_response_hash=raw_response_hash,
                year=row.get("year"),
                month=row.get("month"),
                region_code=row.get("region_code"),
                region_name=row.get("region_name"),
                in_count=row.get("in_count"),
                out_count=row.get("out_count"),
                net_count=row.get("net_count"),
            )
        )
    return records


class KostatMigrationConnector:
    """Connector for KOSTAT population migration data via kpubdata KOSIS API.

    Satisfies ``Connector[KostatMigrationRequest, BronzeMigration]`` protocol.
    """

    source_id: ClassVar[str] = "kostat_population_migration"

    def __init__(
        self,
        client: Dataset,
        rate_limiter: RateLimiter,
        now_fn: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._client = client
        self._rate_limiter = rate_limiter
        self._now_fn = now_fn

    def fetch(self, request: KostatMigrationRequest) -> ConnectorResult[BronzeMigration]:
        """Fetch migration data for one month (all 시도 regions).

        Args:
            request: Partition-scoped KOSTAT query configuration.

        Returns:
            Connector result containing Bronze migration records and ingest manifest.
        """
        now = self._now_fn()

        def _call_api() -> pd.DataFrame:
            self._rate_limiter.wait()
            batch = self._client.list(
                start_date=request.year_month,
                end_date=request.year_month,
                objL1="ALL",
                objL2="ALL",
                itmId="T20+T25+T30",
                prdSe="M",
            )
            return pd.DataFrame(batch.items)

        request_params = {
            "org_id": request.org_id,
            "tbl_id": request.tbl_id,
            "year_month": request.year_month,
        }

        try:
            raw_df = retry(_call_api)
        except Exception as exc:
            manifest = build_manifest(
                source_id=self.source_id,
                api_endpoint="statisticsParameterData",
                request_params=request_params,
                response_count=0,
                ingested_at=now,
                status="failed",
                error_message=str(exc),
            )
            return ConnectorResult(records=[], manifest=manifest)

        # Handle empty response
        if raw_df is None or raw_df.empty:
            manifest = build_manifest(
                source_id=self.source_id,
                api_endpoint="statisticsParameterData",
                request_params=request_params,
                response_count=0,
                ingested_at=now,
                status="success",
            )
            return ConnectorResult(records=[], manifest=manifest)

        # Validate required columns
        missing = REQUIRED_COLUMNS - set(raw_df.columns)
        if missing:
            msg = f"Missing expected columns in KOSIS response: {sorted(missing)}"
            raise NonRetryableError(msg)

        # Filter to aggregate rows (total destination) and target metrics
        filtered = _filter_aggregate_rows(raw_df)
        filtered = _filter_target_metrics(filtered)

        if filtered.empty:
            manifest = build_manifest(
                source_id=self.source_id,
                api_endpoint="statisticsParameterData",
                request_params=request_params,
                response_count=0,
                ingested_at=now,
                status="success",
            )
            return ConnectorResult(records=[], manifest=manifest)

        # Pivot long format → one row per (region, period)
        pivoted_rows = _pivot_to_region_rows(filtered)

        # Hash the pivoted normalized dicts (before Bronze mapping)
        response_hash = sha256_payload(pivoted_rows)

        # Map to Bronze records
        records = _map_to_bronze(
            pivoted_rows,
            source_id=self.source_id,
            ingest_timestamp=now,
            raw_response_hash=response_hash,
        )

        manifest = build_manifest(
            source_id=self.source_id,
            api_endpoint="statisticsParameterData",
            request_params=request_params,
            response_count=len(records),
            ingested_at=now,
            status="success",
        )

        return ConnectorResult(records=records, manifest=manifest)
