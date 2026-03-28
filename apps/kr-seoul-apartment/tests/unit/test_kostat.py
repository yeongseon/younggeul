"""Unit tests for KostatMigrationConnector."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from younggeul_app_kr_seoul_apartment.connectors.kostat import (
    METRIC_MAP,
    REQUIRED_COLUMNS,
    KostatMigrationConnector,
    KostatMigrationRequest,
    _filter_aggregate_rows,
    _filter_target_metrics,
    _pivot_to_region_rows,
    _safe_str,
)
from younggeul_core.connectors.protocol import Connector, ConnectorResult
from younggeul_core.connectors.rate_limit import RateLimiter
from younggeul_core.connectors.retry import ConnectorError, NonRetryableError
from younggeul_core.state.bronze import BronzeMigration

_FIXED_NOW = datetime(2026, 3, 28, 12, 0, 0, tzinfo=timezone.utc)


def _fixed_now() -> datetime:
    return _FIXED_NOW


def _make_rate_limiter() -> RateLimiter:
    return RateLimiter(min_interval=0.0)


def _default_request() -> KostatMigrationRequest:
    return KostatMigrationRequest(year_month="202301")


def _sample_long_dataframe() -> pd.DataFrame:
    """Create a synthetic long-format KOSIS DataFrame.

    Two regions (Seoul 11, Busan 26), each with 3 metrics (T20, T25, T30).
    C2="00" marks aggregate/total rows.
    """
    rows: list[dict[str, Any]] = []
    regions = [("11", "서울특별시"), ("26", "부산광역시")]
    metrics = [
        ("T20", "전입", "150000"),
        ("T25", "전출", "140000"),
        ("T30", "순이동", "10000"),
    ]
    for code, name in regions:
        for itm_id, itm_nm, dt in metrics:
            rows.append(
                {
                    "C1": code,
                    "C1_NM": name,
                    "C2": "00",
                    "C2_NM": "합계",
                    "ITM_ID": itm_id,
                    "ITM_NM": itm_nm,
                    "PRD_DE": "202301",
                    "DT": dt,
                    "TBL_ID": "DT_1B26003_A01",
                    "ORG_ID": "101",
                    "UNIT_NM": "명",
                }
            )
    return pd.DataFrame(rows)


def _sample_with_non_aggregate_rows() -> pd.DataFrame:
    """DataFrame mixing aggregate (C2='00') and non-aggregate (C2='11') rows."""
    rows: list[dict[str, Any]] = [
        # Aggregate row — should be kept
        {
            "C1": "11",
            "C1_NM": "서울특별시",
            "C2": "00",
            "C2_NM": "합계",
            "ITM_ID": "T20",
            "ITM_NM": "전입",
            "PRD_DE": "202301",
            "DT": "150000",
        },
        # Non-aggregate (origin-destination pair) — should be filtered out
        {
            "C1": "11",
            "C1_NM": "서울특별시",
            "C2": "11",
            "C2_NM": "서울특별시",
            "ITM_ID": "T20",
            "ITM_NM": "전입",
            "PRD_DE": "202301",
            "DT": "50000",
        },
    ]
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# _safe_str tests
# ---------------------------------------------------------------------------


class TestSafeStr:
    def test_none_returns_none(self) -> None:
        assert _safe_str(None) is None

    def test_nan_returns_none(self) -> None:
        assert _safe_str(float("nan")) is None

    def test_numpy_nan_returns_none(self) -> None:
        assert _safe_str(np.nan) is None

    def test_string_passthrough(self) -> None:
        assert _safe_str("150000") == "150000"

    def test_whitespace_stripped(self) -> None:
        assert _safe_str("  서울  ") == "서울"

    def test_empty_string_returns_none(self) -> None:
        assert _safe_str("   ") is None


# ---------------------------------------------------------------------------
# _filter_aggregate_rows tests
# ---------------------------------------------------------------------------


class TestFilterAggregateRows:
    def test_keeps_aggregate_rows_only(self) -> None:
        df = _sample_with_non_aggregate_rows()
        filtered = _filter_aggregate_rows(df)
        assert len(filtered) == 1
        assert filtered.iloc[0]["C2"] == "00"

    def test_empty_sentinel_kept(self) -> None:
        """Rows with C2='' (empty) are treated as aggregate."""
        df = pd.DataFrame(
            {
                "C1": ["11"],
                "C1_NM": ["서울특별시"],
                "C2": [""],
                "ITM_ID": ["T20"],
                "PRD_DE": ["202301"],
                "DT": ["100"],
            }
        )
        filtered = _filter_aggregate_rows(df)
        assert len(filtered) == 1

    def test_all_sentinel_kept(self) -> None:
        """Rows with C2='ALL' are treated as aggregate."""
        df = pd.DataFrame(
            {
                "C1": ["11"],
                "C1_NM": ["서울특별시"],
                "C2": ["ALL"],
                "ITM_ID": ["T20"],
                "PRD_DE": ["202301"],
                "DT": ["100"],
            }
        )
        filtered = _filter_aggregate_rows(df)
        assert len(filtered) == 1

    def test_no_c2_column_returns_all(self) -> None:
        """If table has no C2 dimension, all rows are treated as aggregate."""
        df = pd.DataFrame(
            {
                "C1": ["11", "26"],
                "C1_NM": ["서울특별시", "부산광역시"],
                "ITM_ID": ["T20", "T20"],
                "PRD_DE": ["202301", "202301"],
                "DT": ["100", "200"],
            }
        )
        filtered = _filter_aggregate_rows(df)
        assert len(filtered) == 2  # noqa: PLR2004


# ---------------------------------------------------------------------------
# _filter_target_metrics tests
# ---------------------------------------------------------------------------


class TestFilterTargetMetrics:
    def test_keeps_target_metrics(self) -> None:
        df = pd.DataFrame({"ITM_ID": ["T20", "T25", "T30", "T99"]})
        filtered = _filter_target_metrics(df)
        assert len(filtered) == 3  # noqa: PLR2004
        assert set(filtered["ITM_ID"]) == {"T20", "T25", "T30"}

    def test_filters_all_non_target(self) -> None:
        df = pd.DataFrame({"ITM_ID": ["T99", "T01"]})
        filtered = _filter_target_metrics(df)
        assert len(filtered) == 0


# ---------------------------------------------------------------------------
# _pivot_to_region_rows tests
# ---------------------------------------------------------------------------


class TestPivotToRegionRows:
    def test_normal_pivot(self) -> None:
        """Three long rows per region pivot into one dict per region."""
        df = _sample_long_dataframe()
        # Filter to aggregate rows first (all rows in fixture are aggregate)
        filtered = _filter_aggregate_rows(df)
        filtered = _filter_target_metrics(filtered)
        pivoted = _pivot_to_region_rows(filtered)

        assert len(pivoted) == 2  # noqa: PLR2004

        seoul = pivoted[0]  # "11" sorts before "26"
        assert seoul["region_code"] == "11"
        assert seoul["region_name"] == "서울특별시"
        assert seoul["year"] == "2023"
        assert seoul["month"] == "01"
        assert seoul["in_count"] == "150000"
        assert seoul["out_count"] == "140000"
        assert seoul["net_count"] == "10000"

        busan = pivoted[1]
        assert busan["region_code"] == "26"
        assert busan["region_name"] == "부산광역시"

    def test_duplicate_metric_raises_error(self) -> None:
        """Duplicate T20 for same region+period raises NonRetryableError."""
        df = pd.DataFrame(
            {
                "C1": ["11", "11"],
                "C1_NM": ["서울특별시", "서울특별시"],
                "ITM_ID": ["T20", "T20"],
                "PRD_DE": ["202301", "202301"],
                "DT": ["100", "200"],
            }
        )
        with pytest.raises(NonRetryableError, match="Duplicate metric T20"):
            _pivot_to_region_rows(df)

    def test_missing_required_fields_skipped(self) -> None:
        """Rows with missing region_code or prd_de are silently skipped."""
        df = pd.DataFrame(
            {
                "C1": [None, "11"],
                "C1_NM": [None, "서울특별시"],
                "ITM_ID": ["T20", "T20"],
                "PRD_DE": ["202301", "202301"],
                "DT": ["100", "200"],
            }
        )
        pivoted = _pivot_to_region_rows(df)
        assert len(pivoted) == 1
        assert pivoted[0]["region_code"] == "11"

    def test_empty_dataframe(self) -> None:
        df = pd.DataFrame(columns=["C1", "C1_NM", "ITM_ID", "PRD_DE", "DT"])
        pivoted = _pivot_to_region_rows(df)
        assert pivoted == []

    def test_deterministic_ordering(self) -> None:
        """Output is sorted by (region_code, region_name, prd_de)."""
        df = pd.DataFrame(
            {
                "C1": ["26", "11"],
                "C1_NM": ["부산광역시", "서울특별시"],
                "ITM_ID": ["T20", "T20"],
                "PRD_DE": ["202301", "202301"],
                "DT": ["200", "100"],
            }
        )
        pivoted = _pivot_to_region_rows(df)
        assert pivoted[0]["region_code"] == "11"
        assert pivoted[1]["region_code"] == "26"


# ---------------------------------------------------------------------------
# KostatMigrationConnector tests
# ---------------------------------------------------------------------------


class TestKostatMigrationConnector:
    def _make_connector(self, client: MagicMock | None = None) -> tuple[KostatMigrationConnector, MagicMock]:
        mock_client = client or MagicMock()
        connector = KostatMigrationConnector(
            client=mock_client,
            rate_limiter=_make_rate_limiter(),
            now_fn=_fixed_now,
        )
        return connector, mock_client

    def test_satisfies_connector_protocol(self) -> None:
        connector, _ = self._make_connector()
        assert isinstance(connector, Connector)

    def test_full_row_mapping(self) -> None:
        """Map a long-format KOSIS DataFrame to BronzeMigration records."""
        connector, mock_client = self._make_connector()
        mock_client.get_data.return_value = _sample_long_dataframe()

        request = _default_request()
        result = connector.fetch(request)

        assert isinstance(result, ConnectorResult)
        assert len(result.records) == 2  # noqa: PLR2004

        # Seoul (sorted first by region_code "11")
        rec = result.records[0]
        assert isinstance(rec, BronzeMigration)
        assert rec.region_code == "11"
        assert rec.region_name == "서울특별시"
        assert rec.year == "2023"
        assert rec.month == "01"
        assert rec.in_count == "150000"
        assert rec.out_count == "140000"
        assert rec.net_count == "10000"

        # Metadata
        assert rec.source_id == "kostat_population_migration"
        assert rec.ingest_timestamp == _FIXED_NOW
        assert rec.raw_response_hash is not None
        assert len(rec.raw_response_hash) == 64  # noqa: PLR2004

    def test_empty_dataframe_returns_empty_result(self) -> None:
        connector, mock_client = self._make_connector()
        mock_client.get_data.return_value = pd.DataFrame()

        request = _default_request()
        result = connector.fetch(request)

        assert result.records == []
        assert result.manifest.response_count == 0
        assert result.manifest.status == "success"

    def test_none_response_returns_empty_result(self) -> None:
        connector, mock_client = self._make_connector()
        mock_client.get_data.return_value = None

        request = _default_request()
        result = connector.fetch(request)

        assert result.records == []
        assert result.manifest.response_count == 0
        assert result.manifest.status == "success"

    def test_api_failure_returns_failed_manifest(self) -> None:
        connector, mock_client = self._make_connector()
        mock_client.get_data.side_effect = ConnectorError("KOSIS timeout")

        request = _default_request()
        result = connector.fetch(request)

        assert result.records == []
        assert result.manifest.status == "failed"
        assert "KOSIS timeout" in (result.manifest.error_message or "")

    def test_missing_columns_raises_non_retryable(self) -> None:
        connector, mock_client = self._make_connector()
        # DataFrame with only some required columns
        mock_client.get_data.return_value = pd.DataFrame({"C1": ["11"], "DT": ["100"]})

        request = _default_request()
        with pytest.raises(NonRetryableError, match="Missing expected columns"):
            connector.fetch(request)

    def test_manifest_fields_correct(self) -> None:
        connector, mock_client = self._make_connector()
        mock_client.get_data.return_value = _sample_long_dataframe()

        request = _default_request()
        result = connector.fetch(request)

        m = result.manifest
        assert m.source_id == "kostat_population_migration"
        assert m.api_endpoint == "statisticsParameterData"
        assert m.request_params == {
            "org_id": "101",
            "tbl_id": "DT_1B26003_A01",
            "year_month": "202301",
        }
        assert m.response_count == 2  # noqa: PLR2004
        assert m.status == "success"
        assert m.ingested_at == _FIXED_NOW

    def test_rate_limiter_called(self) -> None:
        mock_limiter = MagicMock(spec=RateLimiter)
        mock_client = MagicMock()
        mock_client.get_data.return_value = _sample_long_dataframe()

        connector = KostatMigrationConnector(
            client=mock_client,
            rate_limiter=mock_limiter,
            now_fn=_fixed_now,
        )
        request = _default_request()
        connector.fetch(request)

        mock_limiter.wait.assert_called_once()

    def test_hash_deterministic_for_same_data(self) -> None:
        connector, mock_client = self._make_connector()
        mock_client.get_data.return_value = _sample_long_dataframe()

        request = _default_request()
        r1 = connector.fetch(request)

        mock_client.get_data.return_value = _sample_long_dataframe()
        r2 = connector.fetch(request)

        assert r1.records[0].raw_response_hash == r2.records[0].raw_response_hash

    def test_filtered_to_no_metrics_returns_empty(self) -> None:
        """DataFrame with valid columns but no target metrics → empty result."""
        connector, mock_client = self._make_connector()
        mock_client.get_data.return_value = pd.DataFrame(
            {
                "C1": ["11"],
                "C1_NM": ["서울특별시"],
                "C2": ["00"],
                "ITM_ID": ["T99"],  # Not a target metric
                "ITM_NM": ["기타"],
                "PRD_DE": ["202301"],
                "DT": ["100"],
            }
        )

        request = _default_request()
        result = connector.fetch(request)

        assert result.records == []
        assert result.manifest.response_count == 0
        assert result.manifest.status == "success"

    def test_non_aggregate_rows_excluded(self) -> None:
        """Only aggregate rows (C2='00') are included in the result."""
        connector, mock_client = self._make_connector()
        df = _sample_with_non_aggregate_rows()
        # Add more metrics so we have a complete set for aggregate row
        extra = pd.DataFrame(
            [
                {
                    "C1": "11",
                    "C1_NM": "서울특별시",
                    "C2": "00",
                    "C2_NM": "합계",
                    "ITM_ID": "T25",
                    "ITM_NM": "전출",
                    "PRD_DE": "202301",
                    "DT": "140000",
                },
                {
                    "C1": "11",
                    "C1_NM": "서울특별시",
                    "C2": "00",
                    "C2_NM": "합계",
                    "ITM_ID": "T30",
                    "ITM_NM": "순이동",
                    "PRD_DE": "202301",
                    "DT": "10000",
                },
            ]
        )
        full_df = pd.concat([df, extra], ignore_index=True)
        mock_client.get_data.return_value = full_df

        request = _default_request()
        result = connector.fetch(request)

        # Only 1 region (Seoul, aggregate only)
        assert len(result.records) == 1
        assert result.records[0].in_count == "150000"


# ---------------------------------------------------------------------------
# KostatMigrationRequest tests
# ---------------------------------------------------------------------------


class TestKostatMigrationRequest:
    def test_frozen(self) -> None:
        req = _default_request()
        with pytest.raises(AttributeError):
            req.year_month = "202302"  # type: ignore[misc]

    def test_fields(self) -> None:
        req = _default_request()
        assert req.year_month == "202301"
        assert req.org_id == "101"
        assert req.tbl_id == "DT_1B26003_A01"

    def test_defaults(self) -> None:
        """Default org_id and tbl_id are set correctly."""
        req = KostatMigrationRequest(year_month="202312")
        assert req.org_id == "101"
        assert req.tbl_id == "DT_1B26003_A01"

    def test_custom_fields(self) -> None:
        """Custom org_id and tbl_id override defaults."""
        req = KostatMigrationRequest(
            year_month="202312",
            org_id="999",
            tbl_id="DT_CUSTOM",
        )
        assert req.org_id == "999"
        assert req.tbl_id == "DT_CUSTOM"


# ---------------------------------------------------------------------------
# Constants tests
# ---------------------------------------------------------------------------


class TestConstants:
    def test_required_columns(self) -> None:
        assert REQUIRED_COLUMNS == frozenset({"C1", "C1_NM", "ITM_ID", "ITM_NM", "PRD_DE", "DT"})

    def test_metric_map(self) -> None:
        assert METRIC_MAP == {
            "T20": "in_count",
            "T25": "out_count",
            "T30": "net_count",
        }
