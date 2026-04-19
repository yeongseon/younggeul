from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from kpubdata.core.dataset import Dataset

from younggeul_app_kr_seoul_apartment.pipeline import BronzeInput
from younggeul_app_kr_seoul_apartment.pipeline_live import run_live_ingest
from younggeul_core.connectors.protocol import ConnectorResult
from younggeul_core.state.bronze import (
    BronzeAptTransaction,
    BronzeInterestRate,
)


_NOW = datetime(2026, 4, 19, 12, 0, 0, tzinfo=timezone.utc)


def _apt_record() -> BronzeAptTransaction:
    return BronzeAptTransaction(
        ingest_timestamp=_NOW,
        source_id="molit.apartment.transactions",
        raw_response_hash="hash-apt",
        deal_amount="120000",
        deal_year="2025",
        deal_month="03",
        deal_day="15",
        sgg_code="11680",
    )


def _rate_record() -> BronzeInterestRate:
    return BronzeInterestRate(
        ingest_timestamp=_NOW,
        source_id="bank_of_korea_base_rate",
        raw_response_hash="hash-rate",
        date="2025-03-01",
        rate_type="base_rate",
        rate_value="3.5",
        unit="연%",
    )


def test_run_live_ingest_returns_bronze_input_with_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    apt_records = [_apt_record()]
    rate_records = [_rate_record()]

    from younggeul_app_kr_seoul_apartment import pipeline_live

    monkeypatch.setattr(pipeline_live, "MolitAptConnector", MagicMock())
    monkeypatch.setattr(pipeline_live, "BokInterestRateConnector", MagicMock())
    pipeline_live.MolitAptConnector.return_value.fetch.return_value = ConnectorResult(
        records=apt_records, manifest=MagicMock()
    )
    pipeline_live.BokInterestRateConnector.return_value.fetch.return_value = ConnectorResult(
        records=rate_records, manifest=MagicMock()
    )

    client = MagicMock()
    client.dataset.side_effect = lambda _id: MagicMock(spec=Dataset)

    bronze = run_live_ingest(client=client, lawd_code="11680", deal_ym="202503")

    assert isinstance(bronze, BronzeInput)
    assert bronze.apt_transactions == apt_records
    assert bronze.interest_rates == rate_records
    assert bronze.migrations == []


def test_run_live_ingest_passes_correct_request_params(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from younggeul_app_kr_seoul_apartment import pipeline_live
    from younggeul_app_kr_seoul_apartment.connectors.bok import BokInterestRateRequest
    from younggeul_app_kr_seoul_apartment.connectors.molit import MolitAptRequest

    apt_mock = MagicMock()
    rate_mock = MagicMock()
    apt_mock.return_value.fetch.return_value = ConnectorResult(records=[], manifest=MagicMock())
    rate_mock.return_value.fetch.return_value = ConnectorResult(records=[], manifest=MagicMock())
    monkeypatch.setattr(pipeline_live, "MolitAptConnector", apt_mock)
    monkeypatch.setattr(pipeline_live, "BokInterestRateConnector", rate_mock)

    client = MagicMock()
    client.dataset.side_effect = lambda _id: MagicMock(spec=Dataset)

    run_live_ingest(client=client, lawd_code="11680", deal_ym="202503")

    apt_request = apt_mock.return_value.fetch.call_args.args[0]
    assert isinstance(apt_request, MolitAptRequest)
    assert apt_request.sigungu_code == "11680"
    assert apt_request.year_month == "202503"

    rate_request = rate_mock.return_value.fetch.call_args.args[0]
    assert isinstance(rate_request, BokInterestRateRequest)
    assert rate_request.start_date == "202503"
    assert rate_request.end_date == "202503"
    assert rate_request.frequency == "M"
    assert rate_request.rate_type == "base_rate"


def test_run_live_ingest_resolves_two_kpubdata_datasets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from younggeul_app_kr_seoul_apartment import pipeline_live

    monkeypatch.setattr(pipeline_live, "MolitAptConnector", MagicMock())
    monkeypatch.setattr(pipeline_live, "BokInterestRateConnector", MagicMock())
    pipeline_live.MolitAptConnector.return_value.fetch.return_value = ConnectorResult(records=[], manifest=MagicMock())
    pipeline_live.BokInterestRateConnector.return_value.fetch.return_value = ConnectorResult(
        records=[], manifest=MagicMock()
    )

    client = MagicMock()
    client.dataset.side_effect = lambda _id: MagicMock(spec=Dataset)

    run_live_ingest(client=client, lawd_code="11680", deal_ym="202503")

    dataset_ids = [call.args[0] for call in client.dataset.call_args_list]
    assert dataset_ids == ["datago.apt_trade", "bok.base_rate"]


@pytest.mark.parametrize("bad_code", ["1168", "116800", "1168A", ""])
def test_run_live_ingest_rejects_invalid_lawd_code(bad_code: str) -> None:
    with pytest.raises(ValueError, match="lawd_code must be 5 digits"):
        run_live_ingest(client=MagicMock(), lawd_code=bad_code, deal_ym="202503")


@pytest.mark.parametrize("bad_month", ["20250", "2025033", "2025AB", ""])
def test_run_live_ingest_rejects_invalid_deal_ym(bad_month: str) -> None:
    with pytest.raises(ValueError, match="deal_ym must be YYYYMM"):
        run_live_ingest(client=MagicMock(), lawd_code="11680", deal_ym=bad_month)
