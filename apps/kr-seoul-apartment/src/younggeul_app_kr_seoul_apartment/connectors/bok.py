"""BOK (Bank of Korea) interest rate connector using kpubdata."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import ClassVar

import pandas as pd
from kpubdata.core.dataset import Dataset

from younggeul_core.connectors.hashing import sha256_payload
from younggeul_core.connectors.manifest import build_manifest
from younggeul_core.connectors.protocol import ConnectorResult
from younggeul_core.connectors.rate_limit import RateLimiter
from younggeul_core.connectors.retry import NonRetryableError, retry
from younggeul_core.state.bronze import BronzeInterestRate

# ---------------------------------------------------------------------------
# Required columns from the ECOS StatisticSearch response
# ---------------------------------------------------------------------------
# We validate their presence and extract only what BronzeInterestRate needs.
# ---------------------------------------------------------------------------

REQUIRED_COLUMNS: frozenset[str] = frozenset(
    {
        "TIME",
        "DATA_VALUE",
        "UNIT_NAME",
        "STAT_CODE",
        "ITEM_CODE1",
        "ITEM_NAME1",
    }
)


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True, slots=True)
class BokInterestRateRequest:
    """Partition-scoped request for one interest rate series over a date range.

    Attributes:
        stat_code: ECOS statistics table code (e.g., "722Y001").
        item_code1: Primary item code (e.g., "0101000" for base rate).
        frequency: Query frequency — "D" (daily), "M" (monthly), etc.
        start_date: Start date in frequency-appropriate format (e.g., "20240101" or "202401").
        end_date: End date in frequency-appropriate format.
        rate_type: Normalized internal key (e.g., "base_rate", "loan_rate").
        source_id: Source identifier (e.g., "bank_of_korea_base_rate").
    """

    stat_code: str
    item_code1: str
    frequency: str
    start_date: str
    end_date: str
    rate_type: str
    source_id: str


def _safe_str(value: object) -> str | None:
    """Convert a pandas cell value to str | None.

    - NaN / None → None
    - everything else → str(value), stripped
    """
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or pd.isna(value)):
        return None
    result = str(value).strip()
    return result if result else None


def _normalize_time(time_str: str, frequency: str) -> str:
    """Normalize ECOS TIME value to ISO date string.

    - Daily "YYYYMMDD" → "YYYY-MM-DD"
    - Monthly "YYYYMM" → "YYYY-MM-01"
    - Quarterly "YYYYQ1" → "YYYY-01-01" (first day of quarter)
    - Annual "YYYY" → "YYYY-01-01"
    """
    if frequency == "D" and len(time_str) == 8:  # noqa: PLR2004
        return f"{time_str[:4]}-{time_str[4:6]}-{time_str[6:8]}"
    if frequency == "M" and len(time_str) == 6:  # noqa: PLR2004
        return f"{time_str[:4]}-{time_str[4:6]}-01"
    if frequency == "Q" and len(time_str) == 6:  # noqa: PLR2004
        # "2024Q1" → "2024-01-01", "2024Q2" → "2024-04-01", etc.
        year = time_str[:4]
        quarter = int(time_str[5])
        month = (quarter - 1) * 3 + 1
        return f"{year}-{month:02d}-01"
    if frequency == "A" and len(time_str) == 4:  # noqa: PLR2004
        return f"{time_str}-01-01"
    # Fallback: return as-is
    return time_str


def _normalize_dataframe(
    df: pd.DataFrame,
    *,
    frequency: str,
) -> list[dict[str, object]]:
    """Convert ECOS DataFrame rows to normalized dicts.

    - NaN → None
    - TIME normalized to ISO date
    - All values converted to strings
    - Includes identity columns for hash completeness
    """
    rows: list[dict[str, object]] = []
    for _, series in df.iterrows():
        row: dict[str, object] = {}
        for col in df.columns:
            if col == "TIME":
                raw_time = _safe_str(series[col])
                row[col] = _normalize_time(raw_time, frequency) if raw_time else None
            else:
                row[col] = _safe_str(series[col])
        rows.append(row)
    return rows


def _optional_str(row: dict[str, object], key: str) -> str | None:
    value = row.get(key)
    return value if isinstance(value, str) else None


def _map_to_bronze(
    raw_rows: list[dict[str, object]],
    *,
    rate_type: str,
    source_id: str,
    ingest_timestamp: datetime,
    raw_response_hash: str,
) -> list[BronzeInterestRate]:
    """Map normalized raw dicts to BronzeInterestRate records."""
    records: list[BronzeInterestRate] = []
    for raw in raw_rows:
        records.append(
            BronzeInterestRate(
                ingest_timestamp=ingest_timestamp,
                source_id=source_id,
                raw_response_hash=raw_response_hash,
                date=_optional_str(raw, "TIME"),
                rate_type=rate_type,
                rate_value=_optional_str(raw, "DATA_VALUE"),
                unit=_optional_str(raw, "UNIT_NAME"),
            )
        )
    return records


class BokInterestRateConnector:
    """Connector for BOK interest rate data via kpubdata BOK dataset.

    Satisfies ``Connector[BokInterestRateRequest, BronzeInterestRate]`` protocol.
    """

    source_id: ClassVar[str] = "bank_of_korea_interest_rate"

    def __init__(
        self,
        client: Dataset,
        rate_limiter: RateLimiter,
        now_fn: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._client = client
        self._rate_limiter = rate_limiter
        self._now_fn = now_fn

    def fetch(self, request: BokInterestRateRequest) -> ConnectorResult[BronzeInterestRate]:
        """Fetch interest rate data for one series over a date range.

        Args:
            request: Partition-scoped BOK query configuration.

        Returns:
            Connector result containing Bronze interest-rate records and ingest manifest.
        """
        now = self._now_fn()

        def _call_api() -> pd.DataFrame:
            self._rate_limiter.wait()
            batch = self._client.list(
                start_date=request.start_date,
                end_date=request.end_date,
                frequency=request.frequency,
            )
            result = pd.DataFrame(batch.items)
            return result

        request_params = {
            "stat_code": request.stat_code,
            "item_code1": request.item_code1,
            "frequency": request.frequency,
            "start_date": request.start_date,
            "end_date": request.end_date,
        }

        try:
            raw_df = retry(_call_api)
        except Exception as exc:
            manifest = build_manifest(
                source_id=request.source_id,
                api_endpoint="StatisticSearch",
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
                source_id=request.source_id,
                api_endpoint="StatisticSearch",
                request_params=request_params,
                response_count=0,
                ingested_at=now,
                status="success",
            )
            return ConnectorResult(records=[], manifest=manifest)

        # Validate required columns
        missing = REQUIRED_COLUMNS - set(raw_df.columns)
        if missing:
            msg = f"Missing expected columns in ECOS response: {sorted(missing)}"
            raise NonRetryableError(msg)

        # Stage 1: Normalize (NaN → None, TIME → ISO date)
        raw_rows = _normalize_dataframe(raw_df, frequency=request.frequency)

        # Compute hash from normalized raw dicts (before Bronze mapping)
        response_hash = sha256_payload(raw_rows)

        # Stage 2: Map to Bronze records
        records = _map_to_bronze(
            raw_rows,
            rate_type=request.rate_type,
            source_id=request.source_id,
            ingest_timestamp=now,
            raw_response_hash=response_hash,
        )

        manifest = build_manifest(
            source_id=request.source_id,
            api_endpoint="StatisticSearch",
            request_params=request_params,
            response_count=len(records),
            ingested_at=now,
            status="success",
        )

        return ConnectorResult(records=records, manifest=manifest)
