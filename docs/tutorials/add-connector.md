# How to Add a Data Connector

## Overview

In Younggeul, a connector fetches one partition of external data, normalizes it, maps it to Bronze records, and returns a `ConnectorResult` with a manifest. The pipeline only sees typed Bronze models, so connectors are where source-specific API shape and cleanup logic live. Use the existing MOLIT/BOK/KOSTAT connectors as your implementation template.

## Prerequisites

- You know which upstream API and partition key(s) you need (for example: one `sigungu_code` + one `year_month`).
- You have a Bronze record schema in `younggeul_core.state.bronze` (or will add one) that follows the Bronze convention.
- You can run `pytest` for unit tests in `apps/kr-seoul-apartment/tests/unit`.

## Step 1: Define the Request Model

Use a frozen dataclass for partition-scoped request params.

`MolitAptRequest` in `connectors/molit.py` is the canonical pattern:

```python
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MolitAptRequest:
    """Partition-scoped request for one sigungu + one month."""

    sigungu_code: str
    year_month: str
```

For a new connector, keep the same shape (frozen + explicit partition fields):

```python
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NewLegalDistrictRequest:
    """Partition-scoped request for one region + one month."""

    region_scope: str
    year_month: str
```

## Step 2: Define the Bronze Record Model

Bronze models are Pydantic models in `younggeul_core.state.bronze` and include ingestion metadata via `BronzeIngestMeta`. Convention: source payload fields are `str | None` (raw, minimally interpreted).

Pattern from existing models (`BronzeAptTransaction`, `BronzeInterestRate`, `BronzeMigration`, `BronzeLegalDistrictCode`):

```python
from pydantic import ConfigDict

from younggeul_core.state.bronze import BronzeIngestMeta


class BronzeLegalDistrictCode(BronzeIngestMeta):
    model_config = ConfigDict(str_strip_whitespace=True, frozen=True)

    code: str | None = None
    name: str | None = None
    is_active: str | None = None
```

## Step 3: Implement the Connector Class

Follow the same import and fetch flow used by `MolitAptConnector`, `BokInterestRateConnector`, and `KostatMigrationConnector`.

```python
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, ClassVar

import pandas as pd

from younggeul_core.connectors.hashing import sha256_payload
from younggeul_core.connectors.manifest import build_manifest
from younggeul_core.connectors.protocol import ConnectorResult
from younggeul_core.connectors.rate_limit import RateLimiter
from younggeul_core.connectors.retry import ConnectorError, NonRetryableError, retry
from younggeul_core.state.bronze import BronzeLegalDistrictCode


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _normalize_dataframe(df: pd.DataFrame) -> list[dict[str, Any]]:
    # Keep deterministic row-order, convert NaN->None, stringify values.
    rows: list[dict[str, Any]] = []
    for _, series in df.iterrows():
        rows.append(
            {
                "REGION_CODE": None if pd.isna(series["REGION_CODE"]) else str(series["REGION_CODE"]),
                "REGION_NAME": None if pd.isna(series["REGION_NAME"]) else str(series["REGION_NAME"]),
                "IS_ACTIVE": None if pd.isna(series["IS_ACTIVE"]) else str(series["IS_ACTIVE"]),
            }
        )
    return rows


def _map_to_bronze(
    raw_rows: list[dict[str, Any]],
    *,
    source_id: str,
    ingest_timestamp: datetime,
    raw_response_hash: str,
) -> list[BronzeLegalDistrictCode]:
    return [
        BronzeLegalDistrictCode(
            ingest_timestamp=ingest_timestamp,
            source_id=source_id,
            raw_response_hash=raw_response_hash,
            code=row.get("REGION_CODE"),
            name=row.get("REGION_NAME"),
            is_active=row.get("IS_ACTIVE"),
        )
        for row in raw_rows
    ]


class NewLegalDistrictConnector:
    source_id: ClassVar[str] = "kostat_legal_district_code"

    def __init__(
        self,
        client: Any,
        rate_limiter: RateLimiter,
        now_fn: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._client = client
        self._rate_limiter = rate_limiter
        self._now_fn = now_fn

    def fetch(self, request: NewLegalDistrictRequest) -> ConnectorResult[BronzeLegalDistrictCode]:
        now = self._now_fn()
        request_params = {"region_scope": request.region_scope, "year_month": request.year_month}

        def _call_api() -> pd.DataFrame:
            self._rate_limiter.wait()  # keep this inside retry() callable
            return self._client.get_data(region_scope=request.region_scope, year_month=request.year_month)

        try:
            raw_df = retry(_call_api)
        except Exception as exc:
            if isinstance(exc, ConnectorError) and not exc.retryable:
                raise
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
            return ConnectorResult(
                records=[],
                manifest=build_manifest(
                    source_id=self.source_id,
                    api_endpoint="statisticsParameterData",
                    request_params=request_params,
                    response_count=0,
                    ingested_at=now,
                    status="success",
                ),
            )

        required = {"REGION_CODE", "REGION_NAME", "IS_ACTIVE"}
        missing = required - set(raw_df.columns)
        if missing:
            raise NonRetryableError(f"Missing expected columns: {sorted(missing)}")

        raw_rows = _normalize_dataframe(raw_df)
        response_hash = sha256_payload(raw_rows)
        records = _map_to_bronze(
            raw_rows,
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
```

## Step 4: Write Unit Tests

Mirror `tests/unit/test_molit.py`: mock client, use `RateLimiter(min_interval=0.0)`, inject fixed `now_fn`, and test mapping/manifest/errors/hash.

```python
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pandas as pd
import pytest

from younggeul_core.connectors.rate_limit import RateLimiter
from younggeul_core.connectors.retry import ConnectorError, NonRetryableError

_FIXED_NOW = datetime(2026, 3, 28, 12, 0, 0, tzinfo=timezone.utc)


def _fixed_now() -> datetime:
    return _FIXED_NOW


def _make_connector(client: MagicMock | None = None) -> tuple[NewLegalDistrictConnector, MagicMock]:
    mock_client = client or MagicMock()
    connector = NewLegalDistrictConnector(
        client=mock_client,
        rate_limiter=RateLimiter(min_interval=0.0),
        now_fn=_fixed_now,
    )
    return connector, mock_client


def test_success_mapping() -> None:
    connector, client = _make_connector()
    client.get_data.return_value = pd.DataFrame(
        {
            "REGION_CODE": ["11680"],
            "REGION_NAME": ["강남구"],
            "IS_ACTIVE": ["Y"],
        }
    )

    result = connector.fetch(NewLegalDistrictRequest(region_scope="seoul", year_month="202507"))

    assert len(result.records) == 1
    assert result.records[0].code == "11680"
    assert result.records[0].ingest_timestamp == _FIXED_NOW
    assert result.manifest.status == "success"


def test_failed_manifest_on_error() -> None:
    connector, client = _make_connector()
    client.get_data.side_effect = ConnectorError("API timeout")

    result = connector.fetch(NewLegalDistrictRequest(region_scope="seoul", year_month="202507"))

    assert result.records == []
    assert result.manifest.status == "failed"
    assert "API timeout" in (result.manifest.error_message or "")


def test_missing_columns_raises_non_retryable() -> None:
    connector, client = _make_connector()
    client.get_data.return_value = pd.DataFrame({"REGION_CODE": ["11680"]})

    with pytest.raises(NonRetryableError, match="Missing expected columns"):
        connector.fetch(NewLegalDistrictRequest(region_scope="seoul", year_month="202507"))


def test_hash_deterministic() -> None:
    connector, client = _make_connector()
    df = pd.DataFrame(
        {
            "REGION_CODE": ["11680"],
            "REGION_NAME": ["강남구"],
            "IS_ACTIVE": ["Y"],
        }
    )

    client.get_data.return_value = df
    r1 = connector.fetch(NewLegalDistrictRequest(region_scope="seoul", year_month="202507"))
    client.get_data.return_value = df
    r2 = connector.fetch(NewLegalDistrictRequest(region_scope="seoul", year_month="202507"))

    assert r1.records[0].raw_response_hash == r2.records[0].raw_response_hash
```

## Step 5: Integrate with Ingestion

Connector outputs are just typed Bronze lists + manifests. Convert them into `BronzeInput` and pass to `run_pipeline`.

```python
from younggeul_app_kr_seoul_apartment.pipeline import BronzeInput, run_pipeline

# Example partition loop
molit_records = []
for req in [MolitAptRequest(sigungu_code="11680", year_month="202507")]:
    result = molit_connector.fetch(req)
    molit_records.extend(result.records)
    # persist result.manifest if needed

bronze = BronzeInput(
    apt_transactions=molit_records,
    interest_rates=interest_rate_records,
    migrations=migration_records,
)

pipeline_result = run_pipeline(bronze)
```

## Summary

Checklist:

- [ ] Added a frozen partition request dataclass.
- [ ] Added/confirmed a Bronze Pydantic model with source fields as `str | None`.
- [ ] Implemented connector `fetch()` with: `retry()` + `RateLimiter.wait()` + normalization + `sha256_payload()` + Bronze mapping + `build_manifest()`.
- [ ] Added unit tests for success mapping, failed manifest, missing-column `NonRetryableError`, and deterministic hash.
- [ ] Wired connector records into `BronzeInput` and executed `run_pipeline()`.
