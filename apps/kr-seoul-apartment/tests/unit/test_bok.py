"""Unit tests for BokInterestRateConnector."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from younggeul_app_kr_seoul_apartment.connectors.bok import (
    BokInterestRateConnector,
    BokInterestRateRequest,
    _normalize_dataframe,
    _normalize_time,
    _safe_str,
)
from younggeul_core.connectors.protocol import Connector, ConnectorResult
from younggeul_core.connectors.rate_limit import RateLimiter
from younggeul_core.connectors.retry import ConnectorError, NonRetryableError
from younggeul_core.state.bronze import BronzeInterestRate

_FIXED_NOW = datetime(2026, 3, 28, 12, 0, 0, tzinfo=timezone.utc)


def _fixed_now() -> datetime:
    return _FIXED_NOW


def _make_rate_limiter() -> RateLimiter:
    return RateLimiter(min_interval=0.0)


def _base_rate_request() -> BokInterestRateRequest:
    return BokInterestRateRequest(
        stat_code="722Y001",
        item_code1="0101000",
        frequency="D",
        start_date="20240101",
        end_date="20240131",
        rate_type="base_rate",
        source_id="bank_of_korea_base_rate",
    )


def _monthly_rate_request() -> BokInterestRateRequest:
    return BokInterestRateRequest(
        stat_code="121Y006",
        item_code1="BIS0020",
        frequency="M",
        start_date="202401",
        end_date="202412",
        rate_type="loan_rate",
        source_id="bank_of_korea_loan_rate",
    )


def _sample_daily_dataframe() -> pd.DataFrame:
    """Create a synthetic DataFrame matching ECOS StatisticSearch output (daily)."""
    data: dict[str, list[Any]] = {
        "STAT_CODE": ["722Y001"],
        "STAT_NAME": ["한국은행 기준금리"],
        "ITEM_CODE1": ["0101000"],
        "ITEM_NAME1": ["한국은행 기준금리"],
        "ITEM_CODE2": [" "],
        "ITEM_NAME2": [" "],
        "ITEM_CODE3": [" "],
        "ITEM_NAME3": [" "],
        "ITEM_CODE4": [" "],
        "ITEM_NAME4": [" "],
        "UNIT_NAME": ["%"],
        "WGT": [np.nan],
        "TIME": ["20240115"],
        "DATA_VALUE": ["3.50"],
    }
    return pd.DataFrame(data)


def _sample_monthly_dataframe() -> pd.DataFrame:
    """Create a synthetic DataFrame matching ECOS StatisticSearch output (monthly)."""
    data: dict[str, list[Any]] = {
        "STAT_CODE": ["121Y006", "121Y006"],
        "STAT_NAME": ["예금은행 대출금리", "예금은행 대출금리"],
        "ITEM_CODE1": ["BIS0020", "BIS0020"],
        "ITEM_NAME1": ["주택담보대출금리", "주택담보대출금리"],
        "ITEM_CODE2": [" ", " "],
        "ITEM_NAME2": [" ", " "],
        "ITEM_CODE3": [" ", " "],
        "ITEM_NAME3": [" ", " "],
        "ITEM_CODE4": [" ", " "],
        "ITEM_NAME4": [" ", " "],
        "UNIT_NAME": ["연%", "연%"],
        "WGT": [np.nan, np.nan],
        "TIME": ["202401", "202402"],
        "DATA_VALUE": ["4.28", "4.25"],
    }
    return pd.DataFrame(data)


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
        assert _safe_str("3.50") == "3.50"

    def test_whitespace_stripped(self) -> None:
        assert _safe_str("  hello  ") == "hello"

    def test_empty_string_returns_none(self) -> None:
        assert _safe_str("   ") is None


# ---------------------------------------------------------------------------
# _normalize_time tests
# ---------------------------------------------------------------------------


class TestNormalizeTime:
    def test_daily_to_iso(self) -> None:
        assert _normalize_time("20240115", "D") == "2024-01-15"

    def test_monthly_to_iso_first_day(self) -> None:
        assert _normalize_time("202401", "M") == "2024-01-01"

    def test_quarterly_q1(self) -> None:
        assert _normalize_time("2024Q1", "Q") == "2024-01-01"

    def test_quarterly_q2(self) -> None:
        assert _normalize_time("2024Q2", "Q") == "2024-04-01"

    def test_quarterly_q3(self) -> None:
        assert _normalize_time("2024Q3", "Q") == "2024-07-01"

    def test_quarterly_q4(self) -> None:
        assert _normalize_time("2024Q4", "Q") == "2024-10-01"

    def test_annual_to_iso(self) -> None:
        assert _normalize_time("2024", "A") == "2024-01-01"

    def test_unknown_format_returns_as_is(self) -> None:
        assert _normalize_time("20240115", "X") == "20240115"


# ---------------------------------------------------------------------------
# _normalize_dataframe tests
# ---------------------------------------------------------------------------


class TestNormalizeDataframe:
    def test_nan_converted_to_none(self) -> None:
        df = pd.DataFrame({"WGT": [np.nan], "DATA_VALUE": ["3.50"], "TIME": ["20240101"]})
        rows = _normalize_dataframe(df, frequency="D")
        assert rows[0]["WGT"] is None
        assert rows[0]["DATA_VALUE"] == "3.50"

    def test_time_normalized_daily(self) -> None:
        df = pd.DataFrame({"TIME": ["20240115"], "DATA_VALUE": ["3.50"]})
        rows = _normalize_dataframe(df, frequency="D")
        assert rows[0]["TIME"] == "2024-01-15"

    def test_time_normalized_monthly(self) -> None:
        df = pd.DataFrame({"TIME": ["202401"], "DATA_VALUE": ["3.50"]})
        rows = _normalize_dataframe(df, frequency="M")
        assert rows[0]["TIME"] == "2024-01-01"

    def test_empty_dataframe(self) -> None:
        df = pd.DataFrame()
        rows = _normalize_dataframe(df, frequency="D")
        assert rows == []


# ---------------------------------------------------------------------------
# BokInterestRateConnector tests
# ---------------------------------------------------------------------------


class TestBokInterestRateConnector:
    def _make_connector(self, client: MagicMock | None = None) -> tuple[BokInterestRateConnector, MagicMock]:
        mock_client = client or MagicMock()
        connector = BokInterestRateConnector(
            client=mock_client,
            rate_limiter=_make_rate_limiter(),
            now_fn=_fixed_now,
        )
        return connector, mock_client

    def test_satisfies_connector_protocol(self) -> None:
        connector, _ = self._make_connector()
        assert isinstance(connector, Connector)

    def test_full_row_mapping_daily(self) -> None:
        """Map a daily rate DataFrame row to BronzeInterestRate."""
        connector, mock_client = self._make_connector()
        mock_client.get_statistic_search.return_value = _sample_daily_dataframe()

        request = _base_rate_request()
        result = connector.fetch(request)

        assert isinstance(result, ConnectorResult)
        assert len(result.records) == 1

        rec = result.records[0]
        assert isinstance(rec, BronzeInterestRate)
        assert rec.date == "2024-01-15"
        assert rec.rate_type == "base_rate"
        assert rec.rate_value == "3.50"
        assert rec.unit == "%"
        assert rec.source_id == "bank_of_korea_base_rate"
        assert rec.ingest_timestamp == _FIXED_NOW
        assert rec.raw_response_hash is not None
        assert len(rec.raw_response_hash) == 64  # noqa: PLR2004

    def test_full_row_mapping_monthly(self) -> None:
        """Map monthly rate DataFrame rows to BronzeInterestRate."""
        connector, mock_client = self._make_connector()
        mock_client.get_statistic_search.return_value = _sample_monthly_dataframe()

        request = _monthly_rate_request()
        result = connector.fetch(request)

        assert len(result.records) == 2  # noqa: PLR2004
        assert result.records[0].date == "2024-01-01"
        assert result.records[0].rate_value == "4.28"
        assert result.records[0].rate_type == "loan_rate"
        assert result.records[1].date == "2024-02-01"
        assert result.records[1].rate_value == "4.25"

    def test_empty_dataframe_returns_empty_result(self) -> None:
        connector, mock_client = self._make_connector()
        mock_client.get_statistic_search.return_value = pd.DataFrame()

        request = _base_rate_request()
        result = connector.fetch(request)

        assert result.records == []
        assert result.manifest.response_count == 0
        assert result.manifest.status == "success"

    def test_api_failure_returns_failed_manifest(self) -> None:
        connector, mock_client = self._make_connector()
        mock_client.get_statistic_search.side_effect = ConnectorError("ECOS timeout")

        request = _base_rate_request()
        result = connector.fetch(request)

        assert result.records == []
        assert result.manifest.status == "failed"
        assert "ECOS timeout" in (result.manifest.error_message or "")

    def test_missing_columns_raises_non_retryable(self) -> None:
        connector, mock_client = self._make_connector()
        mock_client.get_statistic_search.return_value = pd.DataFrame({"TIME": ["20240101"], "DATA_VALUE": ["3.50"]})

        request = _base_rate_request()
        with pytest.raises(NonRetryableError, match="Missing expected columns"):
            connector.fetch(request)

    def test_manifest_fields_correct(self) -> None:
        connector, mock_client = self._make_connector()
        mock_client.get_statistic_search.return_value = _sample_daily_dataframe()

        request = _base_rate_request()
        result = connector.fetch(request)

        m = result.manifest
        assert m.source_id == "bank_of_korea_base_rate"
        assert m.api_endpoint == "StatisticSearch"
        assert m.request_params == {
            "stat_code": "722Y001",
            "item_code1": "0101000",
            "frequency": "D",
            "start_date": "20240101",
            "end_date": "20240131",
        }
        assert m.response_count == 1
        assert m.status == "success"
        assert m.ingested_at == _FIXED_NOW

    def test_rate_limiter_called(self) -> None:
        mock_limiter = MagicMock(spec=RateLimiter)
        mock_client = MagicMock()
        mock_client.get_statistic_search.return_value = _sample_daily_dataframe()

        connector = BokInterestRateConnector(
            client=mock_client,
            rate_limiter=mock_limiter,
            now_fn=_fixed_now,
        )
        request = _base_rate_request()
        connector.fetch(request)

        mock_limiter.wait.assert_called_once()

    def test_hash_deterministic_for_same_data(self) -> None:
        connector, mock_client = self._make_connector()
        mock_client.get_statistic_search.return_value = _sample_daily_dataframe()

        request = _base_rate_request()
        r1 = connector.fetch(request)

        mock_client.get_statistic_search.return_value = _sample_daily_dataframe()
        r2 = connector.fetch(request)

        assert r1.records[0].raw_response_hash == r2.records[0].raw_response_hash

    def test_different_series_different_hash(self) -> None:
        """Hashes differ for different series data (identity columns included)."""
        connector, mock_client = self._make_connector()

        mock_client.get_statistic_search.return_value = _sample_daily_dataframe()
        r1 = connector.fetch(_base_rate_request())

        mock_client.get_statistic_search.return_value = _sample_monthly_dataframe()
        r2 = connector.fetch(_monthly_rate_request())

        assert r1.records[0].raw_response_hash != r2.records[0].raw_response_hash


# ---------------------------------------------------------------------------
# BokInterestRateRequest tests
# ---------------------------------------------------------------------------


class TestBokInterestRateRequest:
    def test_frozen(self) -> None:
        req = _base_rate_request()
        with pytest.raises(AttributeError):
            req.stat_code = "999Y999"  # type: ignore[misc]

    def test_fields(self) -> None:
        req = _base_rate_request()
        assert req.stat_code == "722Y001"
        assert req.item_code1 == "0101000"
        assert req.frequency == "D"
        assert req.start_date == "20240101"
        assert req.end_date == "20240131"
        assert req.rate_type == "base_rate"
        assert req.source_id == "bank_of_korea_base_rate"
