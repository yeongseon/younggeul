"""Unit tests for MolitAptConnector."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import cast
from unittest.mock import MagicMock, create_autospec

import numpy as np
import pandas as pd
import pytest
from kpubdata.core.dataset import Dataset
from kpubdata.core.models import DatasetRef, RecordBatch
from kpubdata.core.representation import Representation

from younggeul_app_kr_seoul_apartment.connectors.molit import (
    MolitAptConnector,
    MolitAptRequest,
    _normalize_dataframe,
    _safe_str,
)
from younggeul_core.connectors.protocol import Connector, ConnectorResult
from younggeul_core.connectors.rate_limit import RateLimiter
from younggeul_core.connectors.retry import ConnectorError
from younggeul_core.state.bronze import BronzeAptTransaction

_FIXED_NOW = datetime(2026, 3, 28, 12, 0, 0, tzinfo=timezone.utc)


def _fixed_now() -> datetime:
    return _FIXED_NOW


def _make_rate_limiter() -> RateLimiter:
    return RateLimiter(min_interval=0.0)


def _dataset_ref() -> DatasetRef:
    return DatasetRef(
        id="datago.apt_trade",
        provider="datago",
        dataset_key="apt_trade",
        name="아파트매매 실거래가",
        representation=Representation.API_JSON,
    )


def _make_batch(items: list[dict[str, object]]) -> RecordBatch:
    return RecordBatch(items=items, dataset=_dataset_ref(), total_count=len(items), raw=None)


def _sample_items() -> list[dict[str, object]]:
    return [
        {
            "dealAmount": "82,000",
            "buildYear": "2016",
            "dealYear": "2025",
            "dealMonth": "7",
            "dealDay": "15",
            "umdNm": "역삼동",
            "aptNm": "래미안",
            "floor": "12",
            "excluUseAr": "84.99",
            "jibun": "123-45",
            "sggCd": "11680",
            "aptDong": "101동",
            "roadNm": "테헤란로",
            "roadNmBonbun": "123",
            "roadNmBubun": "1",
            "roadNmCd": "4100001",
            "roadNmSeq": "1",
            "roadNmbCd": "0",
            "bonbun": "123",
            "bubun": "1",
            "landCd": "680",
            "aptSeq": "2025-001",
            "cdealType": np.nan,
            "cdealDay": np.nan,
            "dealingGbn": "중개거래",
            "estateAgentSggNm": "서울 강남구",
            "buyerGbn": "개인",
            "slerGbn": "개인",
            "rgstDate": "20250720",
            "umdCd": "10300",
        }
    ]


class TestSafeStr:
    def test_none_returns_none(self) -> None:
        assert _safe_str(None) is None

    def test_nan_returns_none(self) -> None:
        assert _safe_str(float("nan")) is None

    def test_numpy_nan_returns_none(self) -> None:
        assert _safe_str(np.nan) is None

    def test_int_like_float_with_flag(self) -> None:
        assert _safe_str(2023.0, int_like=True) == "2023"

    def test_int_like_float_without_flag(self) -> None:
        assert _safe_str(2023.0, int_like=False) == "2023.0"

    def test_regular_float(self) -> None:
        assert _safe_str(84.99, int_like=False) == "84.99"

    def test_string_passthrough(self) -> None:
        assert _safe_str("역삼동") == "역삼동"


class TestNormalizeDataframe:
    def test_nan_converted_to_none(self) -> None:
        df = pd.DataFrame({"cdealType": [np.nan], "aptNm": ["래미안"]})
        rows = _normalize_dataframe(df)
        assert rows[0]["cdealType"] is None
        assert rows[0]["aptNm"] == "래미안"

    def test_int_like_floats_normalized(self) -> None:
        df = pd.DataFrame({"buildYear": [2016.0], "sggCd": [11680.0]})
        rows = _normalize_dataframe(df)
        assert rows[0]["buildYear"] == "2016"
        assert rows[0]["sggCd"] == "11680"

    def test_empty_dataframe(self) -> None:
        df = pd.DataFrame()
        rows = _normalize_dataframe(df)
        assert rows == []


class TestMolitAptConnector:
    def _make_connector(self, client: MagicMock | None = None) -> tuple[MolitAptConnector, MagicMock]:
        mock_client = client or cast(MagicMock, create_autospec(Dataset, instance=True, spec_set=True))
        connector = MolitAptConnector(
            client=cast(Dataset, mock_client),
            rate_limiter=_make_rate_limiter(),
            now_fn=_fixed_now,
        )
        return connector, mock_client

    def test_satisfies_connector_protocol(self) -> None:
        connector, _ = self._make_connector()
        assert isinstance(connector, Connector)

    def test_full_row_mapping(self) -> None:
        connector, mock_client = self._make_connector()
        mock_client.list.return_value = _make_batch(_sample_items())

        request = MolitAptRequest(sigungu_code="11680", year_month="202507")
        result = connector.fetch(request)

        assert isinstance(result, ConnectorResult)
        assert len(result.records) == 1

        rec = result.records[0]
        assert isinstance(rec, BronzeAptTransaction)
        assert rec.deal_amount == "82,000"
        assert rec.build_year == "2016"
        assert rec.deal_year == "2025"
        assert rec.deal_month == "7"
        assert rec.deal_day == "15"
        assert rec.dong == "역삼동"
        assert rec.apt_name == "래미안"
        assert rec.floor == "12"
        assert rec.area_exclusive == "84.99"
        assert rec.jibun == "123-45"
        assert rec.regional_code == "11680"
        assert rec.sgg_code == "11680"
        assert rec.apt_dong == "101동"
        assert rec.road_name == "테헤란로"
        assert rec.cancel_deal_type is None  # NaN → None
        assert rec.req_gbn == "중개거래"
        assert rec.registration_date == "20250720"
        assert rec.umd_code == "10300"

        # Metadata
        assert rec.source_id == "molit.apartment.transactions"
        assert rec.ingest_timestamp == _FIXED_NOW
        assert rec.raw_response_hash is not None
        assert len(rec.raw_response_hash) == 64  # noqa: PLR2004

    def test_empty_dataframe_returns_empty_result(self) -> None:
        connector, mock_client = self._make_connector()
        mock_client.list.return_value = _make_batch([])

        request = MolitAptRequest(sigungu_code="11680", year_month="202507")
        result = connector.fetch(request)

        assert result.records == []
        assert result.manifest.response_count == 0
        assert result.manifest.status == "success"

    def test_api_failure_returns_failed_manifest(self) -> None:
        connector, mock_client = self._make_connector()
        mock_client.list.side_effect = ConnectorError("API timeout")

        request = MolitAptRequest(sigungu_code="11680", year_month="202507")
        result = connector.fetch(request)

        assert result.records == []
        assert result.manifest.status == "failed"
        assert "API timeout" in (result.manifest.error_message or "")

    def test_missing_columns_raises_non_retryable(self) -> None:
        connector, mock_client = self._make_connector()
        mock_client.list.return_value = _make_batch([{"dealAmount": "50,000", "aptNm": "래미안"}])

        request = MolitAptRequest(sigungu_code="11680", year_month="202507")
        from younggeul_core.connectors.retry import NonRetryableError

        with pytest.raises(NonRetryableError, match="Missing expected columns"):
            connector.fetch(request)

    def test_manifest_fields_correct(self) -> None:
        connector, mock_client = self._make_connector()
        mock_client.list.return_value = _make_batch(_sample_items())

        request = MolitAptRequest(sigungu_code="11680", year_month="202507")
        result = connector.fetch(request)

        m = result.manifest
        assert m.source_id == "molit.apartment.transactions"
        assert m.api_endpoint == "getRTMSDataSvcAptTradeDev"
        assert m.request_params == {
            "sigungu_code": "11680",
            "year_month": "202507",
        }
        assert m.response_count == 1
        assert m.status == "success"
        assert m.ingested_at == _FIXED_NOW

    def test_rate_limiter_called(self) -> None:
        mock_limiter = MagicMock(spec=RateLimiter)
        mock_client = cast(MagicMock, create_autospec(Dataset, instance=True, spec_set=True))
        mock_client.list.return_value = _make_batch(_sample_items())

        connector = MolitAptConnector(
            client=cast(Dataset, mock_client),
            rate_limiter=mock_limiter,
            now_fn=_fixed_now,
        )
        request = MolitAptRequest(sigungu_code="11680", year_month="202507")
        connector.fetch(request)

        mock_limiter.wait.assert_called_once()

    def test_hash_deterministic_for_same_data(self) -> None:
        connector, mock_client = self._make_connector()
        mock_client.list.return_value = _make_batch(_sample_items())

        request = MolitAptRequest(sigungu_code="11680", year_month="202507")
        r1 = connector.fetch(request)

        mock_client.list.return_value = _make_batch(_sample_items())
        r2 = connector.fetch(request)

        assert r1.records[0].raw_response_hash == r2.records[0].raw_response_hash


class TestMolitAptRequest:
    def test_frozen(self) -> None:
        req = MolitAptRequest(sigungu_code="11680", year_month="202507")
        with pytest.raises(AttributeError):
            setattr(req, "sigungu_code", "99999")

    def test_fields(self) -> None:
        req = MolitAptRequest(sigungu_code="11680", year_month="202507")
        assert req.sigungu_code == "11680"
        assert req.year_month == "202507"
