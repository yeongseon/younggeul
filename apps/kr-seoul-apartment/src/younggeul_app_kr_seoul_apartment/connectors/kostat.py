"""KOSTAT population migration connector using kpubdata KOSIS API.

This connector fetches per-province (시도) net migration from KOSIS table
``DT_1B26003_A01`` (시도별 이동자수) via :mod:`kpubdata`. The dataset exposes
two metrics keyed on (origin C1, destination C2) pairs:

* ``T70`` 이동자수 — gross flow from C1 to C2.
* ``T80`` 순이동자수 — net flow into C2 relative to C1 (positive = inflow).

To populate the per-region ``BronzeMigration`` shape (in / out / net counts)
we collapse the matrix into one row per destination province by filtering
``C1='전국'`` (code ``'00'``):

* ``in_count``  = T70 with C1='00' & C2=region   (전국 → region inflow)
* ``out_count`` = T70 with C1=region & C2='00'   (region → 전국 outflow)
* ``net_count`` = T80 with C1='00' & C2=region   (= in - out by construction)

The emitted ``region_code`` is the 2-digit KOSIS 시도 code (e.g. ``'11'`` for
Seoul). This matches the ``gu_code[:2]`` lookup used by
:func:`younggeul_app_kr_seoul_apartment.transforms.gold_district._find_net_migration`,
so MOLIT lawd codes such as ``11680`` (강남구) join cleanly without an
external mapping table.

The kpubdata client is the only KOSIS-facing dependency (no direct httpx
calls); the wrapper handles authentication via ``KPUBDATA_KOSIS_API_KEY``.
See :doc:`docs/adr/008-kostat-live-activation` for the full rationale.
"""

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

# Required columns from the KOSIS ``DT_1B26003_A01`` payload after kpubdata
# normalisation. Anything else is metadata we ignore.
REQUIRED_COLUMNS: frozenset[str] = frozenset(
    {
        "C1",
        "C1_NM",
        "C2",
        "C2_NM",
        "ITM_ID",
        "PRD_DE",
        "DT",
    }
)

# KOSIS uses ``'00'`` (with display name ``전국``) as the aggregate sentinel
# in the C1/C2 dimensions. Filtering on this code lets us collapse the
# origin × destination matrix into one row per region.
NATIONAL_AGGREGATE_CODE: str = "00"

# Metrics we keep from the response. T70 carries the gross flow used for
# both in_count and out_count (depending on which axis is the aggregate);
# T80 carries the pre-computed net flow.
ITM_GROSS_FLOW: str = "T70"
ITM_NET_FLOW: str = "T80"
TARGET_ITM_IDS: frozenset[str] = frozenset({ITM_GROSS_FLOW, ITM_NET_FLOW})


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True, slots=True)
class KostatMigrationRequest:
    """Partition-scoped request for one month of migration data.

    The connector always queries a single month and returns one
    :class:`BronzeMigration` per non-aggregate destination province present
    in the response.

    Attributes:
        year_month: Period in ``YYYYMM`` format (e.g. ``"202503"``).
        org_id: KOSIS organisation ID. Defaults to ``"101"`` (통계청) and is
            kept as metadata for the manifest only — kpubdata routes by
            dataset id rather than ``orgId``.
        tbl_id: KOSIS table ID. Defaults to ``"DT_1B26003_A01"`` (시도별
            이동자수) which is the only migration table kpubdata exposes.
    """

    year_month: str
    org_id: str = "101"
    tbl_id: str = "DT_1B26003_A01"


def _safe_str(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or pd.isna(value)):
        return None
    result = str(value).strip()
    return result if result else None


def _filter_target_metrics(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["ITM_ID"].astype(str).str.strip().isin(TARGET_ITM_IDS)].copy()


def _pivot_to_region_rows(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Collapse the (C1, C2, ITM_ID) matrix into one dict per destination region.

    Strategy (see module docstring for the rationale):

    * For each row where ``C1 == '00'`` and ``C2 != '00'``:
        - ``ITM_ID == 'T70'`` contributes ``in_count`` (전국 → region).
        - ``ITM_ID == 'T80'`` contributes ``net_count``.
    * For each row where ``C2 == '00'`` and ``C1 != '00'``:
        - ``ITM_ID == 'T70'`` contributes ``out_count`` (region → 전국).
    * Self-loops (``C1 == C2``) and intra-region pairs are skipped because
      they would double-count flows once the matrix is collapsed.

    Raises:
        NonRetryableError: When the same ``(region, period, metric)`` slot
            is filled twice — that signals a malformed payload because each
            (origin, destination, metric) tuple should be unique.
    """
    groups: dict[tuple[str, str], dict[str, Any]] = {}

    def _slot(region_code: str, region_name: str, prd_de: str) -> dict[str, Any]:
        key = (region_code, prd_de)
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
        return groups[key]

    for _, row in df.iterrows():
        c1 = _safe_str(row.get("C1"))
        c2 = _safe_str(row.get("C2"))
        c1_nm = _safe_str(row.get("C1_NM"))
        c2_nm = _safe_str(row.get("C2_NM"))
        prd_de = _safe_str(row.get("PRD_DE"))
        itm_id = _safe_str(row.get("ITM_ID"))
        value = _safe_str(row.get("DT"))

        if not c1 or not c2 or not prd_de or not itm_id:
            continue

        # In = T70 with origin=전국, destination=region
        if c1 == NATIONAL_AGGREGATE_CODE and c2 != NATIONAL_AGGREGATE_CODE:
            slot = _slot(c2, c2_nm or "", prd_de)
            if itm_id == ITM_GROSS_FLOW:
                if slot["in_count"] is not None:
                    msg = f"Duplicate in_count for region={c2} period={prd_de}"
                    raise NonRetryableError(msg)
                slot["in_count"] = value
            elif itm_id == ITM_NET_FLOW:
                if slot["net_count"] is not None:
                    msg = f"Duplicate net_count for region={c2} period={prd_de}"
                    raise NonRetryableError(msg)
                slot["net_count"] = value
        # Out = T70 with origin=region, destination=전국 (T80 here would be
        # the negation of the inflow row, so we ignore it to avoid duplication)
        elif c2 == NATIONAL_AGGREGATE_CODE and c1 != NATIONAL_AGGREGATE_CODE:
            if itm_id == ITM_GROSS_FLOW:
                slot = _slot(c1, c1_nm or "", prd_de)
                if slot["out_count"] is not None:
                    msg = f"Duplicate out_count for region={c1} period={prd_de}"
                    raise NonRetryableError(msg)
                slot["out_count"] = value
        # Skip C1==C2 self-loops and inter-region pairs — they don't map to
        # the per-region in/out/net schema.

    # Deterministic ordering for downstream hashing & snapshots.
    return [groups[k] for k in sorted(groups.keys())]


def _map_to_bronze(
    pivoted_rows: list[dict[str, Any]],
    *,
    source_id: str,
    ingest_timestamp: datetime,
    raw_response_hash: str,
) -> list[BronzeMigration]:
    return [
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
        for row in pivoted_rows
    ]


class KostatMigrationConnector:
    """Connector for KOSTAT population migration via the kpubdata KOSIS API.

    Satisfies ``Connector[KostatMigrationRequest, BronzeMigration]``.
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
        """Fetch one month of 시도-level migration and return Bronze records.

        The kpubdata ``list`` operation returns the full origin × destination
        matrix; we collapse it to one row per destination province using
        :func:`_pivot_to_region_rows` (see that function for axis semantics).

        Args:
            request: Partition-scoped query configuration.

        Returns:
            ``ConnectorResult`` containing zero or more ``BronzeMigration``
            records (one per non-aggregate destination province) plus an
            ingest manifest describing the call.
        """
        now = self._now_fn()

        def _call_api() -> pd.DataFrame:
            self._rate_limiter.wait()
            batch = self._client.list(
                start_date=request.year_month,
                end_date=request.year_month,
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

        missing = REQUIRED_COLUMNS - set(raw_df.columns)
        if missing:
            msg = f"Missing expected columns in KOSIS response: {sorted(missing)}"
            raise NonRetryableError(msg)

        filtered = _filter_target_metrics(raw_df)

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

        pivoted_rows = _pivot_to_region_rows(filtered)
        response_hash = sha256_payload(pivoted_rows)

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
