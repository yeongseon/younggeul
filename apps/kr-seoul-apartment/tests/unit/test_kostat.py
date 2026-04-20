from __future__ import annotations

from datetime import datetime, timezone
from typing import cast
from unittest.mock import MagicMock

import pandas as pd
import pytest
from kpubdata.core.dataset import Dataset
from kpubdata.core.models import DatasetRef, RecordBatch
from kpubdata.core.representation import Representation

from younggeul_app_kr_seoul_apartment.connectors.kostat import (
    NATIONAL_AGGREGATE_CODE,
    REQUIRED_COLUMNS,
    TARGET_ITM_IDS,
    KostatMigrationConnector,
    KostatMigrationRequest,
    _filter_target_metrics,
    _pivot_to_region_rows,
    _safe_str,
)
from younggeul_core.connectors.protocol import Connector, ConnectorResult
from younggeul_core.connectors.rate_limit import RateLimiter
from younggeul_core.connectors.retry import NonRetryableError
from younggeul_core.state.bronze import BronzeMigration

_FIXED_NOW = datetime(2026, 3, 28, 12, 0, 0, tzinfo=timezone.utc)


def _fixed_now() -> datetime:
    return _FIXED_NOW


def _make_rate_limiter() -> RateLimiter:
    return RateLimiter(min_interval=0.0)


def _default_request() -> KostatMigrationRequest:
    return KostatMigrationRequest(year_month="202503")


def _dataset_ref() -> DatasetRef:
    return DatasetRef(
        id="kosis.population_migration",
        provider="kosis",
        dataset_key="population_migration",
        name="시도별 이동자수",
        representation=Representation.API_JSON,
    )


def _record_batch(items: list[dict[str, object]]) -> RecordBatch:
    return RecordBatch(items=items, dataset=_dataset_ref(), total_count=len(items), raw=items)


def _flow_row(
    *,
    c1: str,
    c1_nm: str,
    c2: str,
    c2_nm: str,
    itm_id: str,
    dt: str,
    prd_de: str = "202503",
) -> dict[str, object]:
    return {
        "C1": c1,
        "C1_NM": c1_nm,
        "C2": c2,
        "C2_NM": c2_nm,
        "ITM_ID": itm_id,
        "ITM_NM": "이동자수" if itm_id == "T70" else "순이동자수",
        "PRD_DE": prd_de,
        "DT": dt,
    }


def _seoul_full_payload(prd_de: str = "202503") -> list[dict[str, object]]:
    """Minimal but realistic 2-region (Seoul, Busan) matrix.

    Includes the four canonical pair types used by the pivot:
    전국→region (in), region→전국 (out), self-loop (skipped),
    inter-region (skipped). Both T70 and T80 metrics are present where
    KOSIS would emit them.
    """
    return [
        # Seoul as destination from 전국: in_count=110859, net_count=1306
        _flow_row(c1="00", c1_nm="전국", c2="11", c2_nm="서울특별시", itm_id="T70", dt="110859", prd_de=prd_de),
        _flow_row(c1="00", c1_nm="전국", c2="11", c2_nm="서울특별시", itm_id="T80", dt="1306", prd_de=prd_de),
        # Seoul as origin to 전국: out_count=109553
        _flow_row(c1="11", c1_nm="서울특별시", c2="00", c2_nm="전국", itm_id="T70", dt="109553", prd_de=prd_de),
        _flow_row(c1="11", c1_nm="서울특별시", c2="00", c2_nm="전국", itm_id="T80", dt="-1306", prd_de=prd_de),
        # Busan as destination: in=20000, net=-500
        _flow_row(c1="00", c1_nm="전국", c2="26", c2_nm="부산광역시", itm_id="T70", dt="20000", prd_de=prd_de),
        _flow_row(c1="00", c1_nm="전국", c2="26", c2_nm="부산광역시", itm_id="T80", dt="-500", prd_de=prd_de),
        # Busan as origin: out=20500
        _flow_row(c1="26", c1_nm="부산광역시", c2="00", c2_nm="전국", itm_id="T70", dt="20500", prd_de=prd_de),
        # Self-loop Seoul→Seoul: must be ignored
        _flow_row(c1="11", c1_nm="서울특별시", c2="11", c2_nm="서울특별시", itm_id="T70", dt="67244", prd_de=prd_de),
        # Inter-region Seoul→Busan: must be ignored
        _flow_row(c1="11", c1_nm="서울특별시", c2="26", c2_nm="부산광역시", itm_id="T70", dt="3000", prd_de=prd_de),
    ]


class TestSafeStr:
    def test_none(self) -> None:
        assert _safe_str(None) is None

    def test_nan(self) -> None:
        assert _safe_str(float("nan")) is None

    def test_whitespace(self) -> None:
        assert _safe_str("   ") is None

    def test_strips(self) -> None:
        assert _safe_str("  hello  ") == "hello"

    def test_int(self) -> None:
        assert _safe_str(42) == "42"


class TestFilterTargetMetrics:
    def test_keeps_t70_and_t80(self) -> None:
        df = pd.DataFrame(
            {
                "ITM_ID": ["T70", "T80", "T75", "X99"],
                "DT": ["1", "2", "3", "4"],
            }
        )
        out = _filter_target_metrics(df)
        assert sorted(out["ITM_ID"].tolist()) == ["T70", "T80"]


class TestPivotToRegionRows:
    def test_full_payload_collapses_to_per_region(self) -> None:
        df = pd.DataFrame(_seoul_full_payload())
        out = _pivot_to_region_rows(df)

        by_code = {row["region_code"]: row for row in out}
        assert set(by_code) == {"11", "26"}

        seoul = by_code["11"]
        assert seoul["region_name"] == "서울특별시"
        assert seoul["year"] == "2025"
        assert seoul["month"] == "03"
        assert seoul["in_count"] == "110859"
        assert seoul["out_count"] == "109553"
        assert seoul["net_count"] == "1306"

        busan = by_code["26"]
        assert busan["in_count"] == "20000"
        assert busan["out_count"] == "20500"
        assert busan["net_count"] == "-500"

    def test_skips_self_loops_and_interregion(self) -> None:
        df = pd.DataFrame(
            [
                _flow_row(c1="11", c1_nm="서울", c2="11", c2_nm="서울", itm_id="T70", dt="999"),
                _flow_row(c1="11", c1_nm="서울", c2="26", c2_nm="부산", itm_id="T70", dt="999"),
            ]
        )
        assert _pivot_to_region_rows(df) == []

    def test_partial_row_missing_only_net(self) -> None:
        df = pd.DataFrame(
            [
                _flow_row(c1="00", c1_nm="전국", c2="11", c2_nm="서울", itm_id="T70", dt="100"),
                _flow_row(c1="11", c1_nm="서울", c2="00", c2_nm="전국", itm_id="T70", dt="80"),
            ]
        )
        out = _pivot_to_region_rows(df)
        assert len(out) == 1
        assert out[0]["in_count"] == "100"
        assert out[0]["out_count"] == "80"
        assert out[0]["net_count"] is None

    def test_duplicate_in_count_raises(self) -> None:
        df = pd.DataFrame(
            [
                _flow_row(c1="00", c1_nm="전국", c2="11", c2_nm="서울", itm_id="T70", dt="100"),
                _flow_row(c1="00", c1_nm="전국", c2="11", c2_nm="서울", itm_id="T70", dt="200"),
            ]
        )
        with pytest.raises(NonRetryableError, match="Duplicate in_count"):
            _pivot_to_region_rows(df)

    def test_duplicate_out_count_raises(self) -> None:
        df = pd.DataFrame(
            [
                _flow_row(c1="11", c1_nm="서울", c2="00", c2_nm="전국", itm_id="T70", dt="100"),
                _flow_row(c1="11", c1_nm="서울", c2="00", c2_nm="전국", itm_id="T70", dt="200"),
            ]
        )
        with pytest.raises(NonRetryableError, match="Duplicate out_count"):
            _pivot_to_region_rows(df)

    def test_duplicate_net_count_raises(self) -> None:
        df = pd.DataFrame(
            [
                _flow_row(c1="00", c1_nm="전국", c2="11", c2_nm="서울", itm_id="T80", dt="10"),
                _flow_row(c1="00", c1_nm="전국", c2="11", c2_nm="서울", itm_id="T80", dt="20"),
            ]
        )
        with pytest.raises(NonRetryableError, match="Duplicate net_count"):
            _pivot_to_region_rows(df)

    def test_deterministic_ordering_by_region_code(self) -> None:
        rows = _seoul_full_payload()
        df = pd.DataFrame(list(reversed(rows)))
        out = _pivot_to_region_rows(df)
        assert [row["region_code"] for row in out] == ["11", "26"]

    def test_skips_rows_with_missing_keys(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "C1": None,
                    "C1_NM": None,
                    "C2": "11",
                    "C2_NM": "서울",
                    "ITM_ID": "T70",
                    "PRD_DE": "202503",
                    "DT": "1",
                },
                {
                    "C1": "00",
                    "C1_NM": "전국",
                    "C2": None,
                    "C2_NM": None,
                    "ITM_ID": "T70",
                    "PRD_DE": "202503",
                    "DT": "1",
                },
                {
                    "C1": "00",
                    "C1_NM": "전국",
                    "C2": "11",
                    "C2_NM": "서울",
                    "ITM_ID": None,
                    "PRD_DE": "202503",
                    "DT": "1",
                },
            ]
        )
        assert _pivot_to_region_rows(df) == []


class TestKostatMigrationConnector:
    def _make_connector(self, client: MagicMock | None = None) -> tuple[KostatMigrationConnector, MagicMock]:
        mock_client = client or MagicMock(spec=Dataset)
        connector = KostatMigrationConnector(
            client=mock_client,
            rate_limiter=_make_rate_limiter(),
            now_fn=_fixed_now,
        )
        return connector, mock_client

    def test_satisfies_connector_protocol(self) -> None:
        connector, _ = self._make_connector()
        assert isinstance(connector, Connector)

    def test_full_payload_emits_one_record_per_region(self) -> None:
        connector, mock_client = self._make_connector()
        mock_client.list.return_value = _record_batch(_seoul_full_payload())

        result = connector.fetch(_default_request())

        assert isinstance(result, ConnectorResult)
        assert len(result.records) == 2  # noqa: PLR2004
        seoul = next(r for r in result.records if r.region_code == "11")
        assert isinstance(seoul, BronzeMigration)
        assert seoul.region_name == "서울특별시"
        assert seoul.year == "2025"
        assert seoul.month == "03"
        assert seoul.in_count == "110859"
        assert seoul.out_count == "109553"
        assert seoul.net_count == "1306"
        assert seoul.source_id == "kostat_population_migration"
        assert seoul.ingest_timestamp == _FIXED_NOW
        assert seoul.raw_response_hash is not None
        assert len(seoul.raw_response_hash) == 64  # noqa: PLR2004

    def test_calls_client_with_year_month_window(self) -> None:
        connector, mock_client = self._make_connector()
        mock_client.list.return_value = _record_batch(_seoul_full_payload())

        connector.fetch(KostatMigrationRequest(year_month="202503"))

        mock_client.list.assert_called_once_with(start_date="202503", end_date="202503")

    def test_empty_batch_returns_empty_success(self) -> None:
        connector, mock_client = self._make_connector()
        mock_client.list.return_value = _record_batch([])

        result = connector.fetch(_default_request())

        assert result.records == []
        assert result.manifest.response_count == 0
        assert result.manifest.status == "success"

    def test_no_target_metrics_returns_empty_success(self) -> None:
        connector, mock_client = self._make_connector()
        mock_client.list.return_value = _record_batch(
            [_flow_row(c1="00", c1_nm="전국", c2="11", c2_nm="서울", itm_id="T99", dt="1")]
        )

        result = connector.fetch(_default_request())

        assert result.records == []
        assert result.manifest.status == "success"

    def test_missing_required_columns_raises(self) -> None:
        connector, mock_client = self._make_connector()
        mock_client.list.return_value = _record_batch([{"C1": "00", "DT": "1"}])

        with pytest.raises(NonRetryableError, match="Missing expected columns"):
            connector.fetch(_default_request())

    def test_api_failure_returns_failed_manifest(self) -> None:
        connector, mock_client = self._make_connector()
        mock_client.list.side_effect = RuntimeError("boom")

        result = connector.fetch(_default_request())

        assert result.records == []
        assert result.manifest.status == "failed"
        assert result.manifest.error_message is not None
        assert "boom" in result.manifest.error_message

    def test_manifest_carries_request_params(self) -> None:
        connector, mock_client = self._make_connector()
        mock_client.list.return_value = _record_batch(_seoul_full_payload())

        result = connector.fetch(KostatMigrationRequest(year_month="202503"))

        params = cast(dict[str, str], result.manifest.request_params)
        assert params["year_month"] == "202503"
        assert params["tbl_id"] == "DT_1B26003_A01"
        assert params["org_id"] == "101"

    def test_response_hash_is_stable_across_calls(self) -> None:
        connector, mock_client = self._make_connector()
        mock_client.list.return_value = _record_batch(_seoul_full_payload())
        first = connector.fetch(_default_request())
        mock_client.list.return_value = _record_batch(_seoul_full_payload())
        second = connector.fetch(_default_request())

        first_hash = first.records[0].raw_response_hash
        second_hash = second.records[0].raw_response_hash
        assert first_hash == second_hash


class TestKostatMigrationRequest:
    def test_defaults(self) -> None:
        req = KostatMigrationRequest(year_month="202503")
        assert req.org_id == "101"
        assert req.tbl_id == "DT_1B26003_A01"

    def test_overrides(self) -> None:
        req = KostatMigrationRequest(year_month="202503", org_id="999", tbl_id="DT_X")
        assert req.org_id == "999"
        assert req.tbl_id == "DT_X"


def test_constants_exported() -> None:
    assert NATIONAL_AGGREGATE_CODE == "00"
    assert TARGET_ITM_IDS == frozenset({"T70", "T80"})
    assert REQUIRED_COLUMNS == frozenset({"C1", "C1_NM", "C2", "C2_NM", "ITM_ID", "PRD_DE", "DT"})
