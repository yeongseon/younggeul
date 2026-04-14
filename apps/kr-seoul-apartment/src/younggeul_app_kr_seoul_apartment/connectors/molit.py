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
from younggeul_core.state.bronze import BronzeAptTransaction

COLUMN_MAP: dict[str, str] = {
    "dealAmount": "deal_amount",
    "buildYear": "build_year",
    "dealYear": "deal_year",
    "dealMonth": "deal_month",
    "dealDay": "deal_day",
    "umdNm": "dong",
    "aptNm": "apt_name",
    "floor": "floor",
    "excluUseAr": "area_exclusive",
    "jibun": "jibun",
    "sggCd": "regional_code",
    "aptDong": "apt_dong",
    "roadNm": "road_name",
    "roadNmBonbun": "road_name_bonbun",
    "roadNmBubun": "road_name_bubun",
    "roadNmCd": "road_name_code",
    "roadNmSeq": "road_name_seq",
    "roadNmBasementCd": "road_name_basement",
    "bonbun": "bonbun",
    "bubun": "bubun",
    "landCd": "land_code",
    "slerGbn": "seller_gbn",
    "buyerGbn": "buyer_gbn",
    "aptSeq": "serial_number",
    "cdealType": "cancel_deal_type",
    "cdealDay": "cancel_deal_day",
    "dealingGbn": "req_gbn",
    "estateAgentSggNm": "rdealer_lawdnm",
    "rgstDate": "registration_date",
    "umdCd": "umd_code",
}

# Fields that are numeric in pandas but should be clean integer strings
# (e.g., 2023.0 → "2023", 11650.0 → "11650")
_INT_LIKE_FIELDS: frozenset[str] = frozenset(
    {
        "buildYear",
        "dealYear",
        "dealMonth",
        "dealDay",
        "floor",
        "sggCd",
        "roadNmBonbun",
        "roadNmBubun",
        "roadNmCd",
        "roadNmSeq",
        "roadNmBasementCd",
        "bonbun",
        "bubun",
        "landCd",
        "umdCd",
    }
)


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True, slots=True)
class MolitAptRequest:
    """Partition-scoped request for one sigungu + one month."""

    sigungu_code: str
    year_month: str


def _safe_str(value: object, *, int_like: bool = False) -> str | None:
    """Convert a pandas cell value to str | None.

    - NaN / None → None
    - float that represents an integer (e.g. 2023.0) → "2023" when int_like=True
    - everything else → str(value)
    """
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or pd.isna(value)):
        return None
    if int_like and isinstance(value, float) and value == int(value):
        return str(int(value))
    return str(value)


def _normalize_dataframe(df: pd.DataFrame) -> list[dict[str, object | None]]:
    rows: list[dict[str, object | None]] = []
    for _, series in df.iterrows():
        row: dict[str, object | None] = {}
        for col in df.columns:
            row[col] = _safe_str(series[col], int_like=col in _INT_LIKE_FIELDS)
        rows.append(row)
    return rows


def _map_to_bronze(
    raw_rows: list[dict[str, object | None]],
    *,
    source_id: str,
    ingest_timestamp: datetime,
    raw_response_hash: str,
) -> list[BronzeAptTransaction]:
    records: list[BronzeAptTransaction] = []
    for raw in raw_rows:
        mapped: dict[str, Any] = {
            "ingest_timestamp": ingest_timestamp,
            "source_id": source_id,
            "raw_response_hash": raw_response_hash,
        }
        for raw_col, bronze_field in COLUMN_MAP.items():
            mapped[bronze_field] = raw.get(raw_col)

        sgg_value = raw.get("sggCd")
        if sgg_value is not None:
            mapped["sgg_code"] = sgg_value

        records.append(BronzeAptTransaction(**mapped))
    return records


class MolitAptConnector:
    """Connector for MOLIT apartment transaction data via kpubdata.

    Satisfies ``Connector[MolitAptRequest, BronzeAptTransaction]`` protocol.
    """

    source_id: ClassVar[str] = "molit.apartment.transactions"

    def __init__(
        self,
        client: Dataset,
        rate_limiter: RateLimiter,
        now_fn: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._client = client
        self._rate_limiter = rate_limiter
        self._now_fn = now_fn

    def fetch(self, request: MolitAptRequest) -> ConnectorResult[BronzeAptTransaction]:
        """Fetch apartment transactions for one sigungu + one month.

        Args:
            request: Partition-scoped MOLIT query configuration.

        Returns:
            Connector result containing Bronze apartment records and ingest manifest.
        """
        now = self._now_fn()

        # Retry wraps only the API call; rate limit inside retried callable
        def _call_api() -> pd.DataFrame:
            self._rate_limiter.wait()
            batch = self._client.list(
                LAWD_CD=request.sigungu_code,
                DEAL_YMD=request.year_month,
            )
            result = pd.DataFrame(batch.items)
            return result

        try:
            raw_df = retry(_call_api)
        except Exception as exc:
            # Build a failed manifest and re-raise
            manifest = build_manifest(
                source_id=self.source_id,
                api_endpoint="getRTMSDataSvcAptTradeDev",
                request_params={
                    "sigungu_code": request.sigungu_code,
                    "year_month": request.year_month,
                },
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
                api_endpoint="getRTMSDataSvcAptTradeDev",
                request_params={
                    "sigungu_code": request.sigungu_code,
                    "year_month": request.year_month,
                },
                response_count=0,
                ingested_at=now,
                status="success",
            )
            return ConnectorResult(records=[], manifest=manifest)

        # Validate expected columns exist
        missing = set(COLUMN_MAP.keys()) - set(raw_df.columns)
        if missing:
            msg = f"Missing expected columns in MOLIT response: {sorted(missing)}"
            raise NonRetryableError(msg)

        # Stage 1: Normalize (NaN → None, float fix)
        raw_rows = _normalize_dataframe(raw_df)

        # Compute hash from normalized raw dicts (before Bronze mapping)
        response_hash = sha256_payload(raw_rows)

        # Stage 2: Map to Bronze records
        records = _map_to_bronze(
            raw_rows,
            source_id=self.source_id,
            ingest_timestamp=now,
            raw_response_hash=response_hash,
        )

        manifest = build_manifest(
            source_id=self.source_id,
            api_endpoint="getRTMSDataSvcAptTradeDev",
            request_params={
                "sigungu_code": request.sigungu_code,
                "year_month": request.year_month,
            },
            response_count=len(records),
            ingested_at=now,
            status="success",
        )

        return ConnectorResult(records=records, manifest=manifest)
