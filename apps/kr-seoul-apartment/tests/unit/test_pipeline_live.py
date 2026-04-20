from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from kpubdata.core.dataset import Dataset

from younggeul_app_kr_seoul_apartment.pipeline import BronzeInput
from younggeul_app_kr_seoul_apartment.pipeline_live import (
    run_live_ingest,
    run_live_ingest_gus_months,
    run_live_ingest_months,
)
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
    _kostat_mock = MagicMock()
    _kostat_mock.return_value.fetch.return_value = ConnectorResult(records=[], manifest=MagicMock())
    monkeypatch.setattr(pipeline_live, "KostatMigrationConnector", _kostat_mock)
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
    _kostat_mock = MagicMock()
    _kostat_mock.return_value.fetch.return_value = ConnectorResult(records=[], manifest=MagicMock())
    monkeypatch.setattr(pipeline_live, "KostatMigrationConnector", _kostat_mock)

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
    _kostat_mock = MagicMock()
    _kostat_mock.return_value.fetch.return_value = ConnectorResult(records=[], manifest=MagicMock())
    monkeypatch.setattr(pipeline_live, "KostatMigrationConnector", _kostat_mock)
    pipeline_live.MolitAptConnector.return_value.fetch.return_value = ConnectorResult(records=[], manifest=MagicMock())
    pipeline_live.BokInterestRateConnector.return_value.fetch.return_value = ConnectorResult(
        records=[], manifest=MagicMock()
    )

    client = MagicMock()
    client.dataset.side_effect = lambda _id: MagicMock(spec=Dataset)

    run_live_ingest(client=client, lawd_code="11680", deal_ym="202503")

    dataset_ids = [call.args[0] for call in client.dataset.call_args_list]
    assert dataset_ids == ["datago.apt_trade", "bok.base_rate", "kosis.population_migration"]


@pytest.mark.parametrize("bad_code", ["1168", "116800", "1168A", ""])
def test_run_live_ingest_rejects_invalid_lawd_code(bad_code: str) -> None:
    with pytest.raises(ValueError, match="lawd_code must be 5 digits"):
        run_live_ingest(client=MagicMock(), lawd_code=bad_code, deal_ym="202503")


@pytest.mark.parametrize("bad_month", ["20250", "2025033", "2025AB", ""])
def test_run_live_ingest_rejects_invalid_deal_ym(bad_month: str) -> None:
    with pytest.raises(ValueError, match="deal_ym must be YYYYMM"):
        run_live_ingest(client=MagicMock(), lawd_code="11680", deal_ym=bad_month)


def test_run_live_ingest_months_fetches_apt_per_month_and_bok_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from younggeul_app_kr_seoul_apartment import pipeline_live
    from younggeul_app_kr_seoul_apartment.connectors.bok import BokInterestRateRequest
    from younggeul_app_kr_seoul_apartment.connectors.molit import MolitAptRequest

    apt_mock = MagicMock()
    rate_mock = MagicMock()
    apt_mock.return_value.fetch.return_value = ConnectorResult(records=[_apt_record()], manifest=MagicMock())
    rate_mock.return_value.fetch.return_value = ConnectorResult(records=[_rate_record()], manifest=MagicMock())
    monkeypatch.setattr(pipeline_live, "MolitAptConnector", apt_mock)
    monkeypatch.setattr(pipeline_live, "BokInterestRateConnector", rate_mock)
    _kostat_mock = MagicMock()
    _kostat_mock.return_value.fetch.return_value = ConnectorResult(records=[], manifest=MagicMock())
    monkeypatch.setattr(pipeline_live, "KostatMigrationConnector", _kostat_mock)

    client = MagicMock()
    client.dataset.side_effect = lambda _id: MagicMock(spec=Dataset)

    bronze = run_live_ingest_months(client=client, lawd_code="11680", deal_yms=["202503", "202403"])

    apt_calls = apt_mock.return_value.fetch.call_args_list
    assert len(apt_calls) == 2
    apt_year_months = [call.args[0].year_month for call in apt_calls]
    assert apt_year_months == ["202503", "202403"]
    for call in apt_calls:
        assert isinstance(call.args[0], MolitAptRequest)
        assert call.args[0].sigungu_code == "11680"

    rate_calls = rate_mock.return_value.fetch.call_args_list
    assert len(rate_calls) == 1
    rate_request = rate_calls[0].args[0]
    assert isinstance(rate_request, BokInterestRateRequest)
    assert rate_request.start_date == "202403"
    assert rate_request.end_date == "202503"

    assert isinstance(bronze, BronzeInput)
    assert len(bronze.apt_transactions) == 2
    assert bronze.migrations == []


def test_run_live_ingest_months_rejects_empty_list() -> None:
    with pytest.raises(ValueError, match="deal_yms must not be empty"):
        run_live_ingest_months(client=MagicMock(), lawd_code="11680", deal_yms=[])


def test_run_live_ingest_months_rejects_duplicates() -> None:
    with pytest.raises(ValueError, match="must not contain duplicates"):
        run_live_ingest_months(client=MagicMock(), lawd_code="11680", deal_yms=["202503", "202503"])


def test_run_live_ingest_months_rejects_invalid_member() -> None:
    with pytest.raises(ValueError, match="deal_ym must be YYYYMM"):
        run_live_ingest_months(client=MagicMock(), lawd_code="11680", deal_yms=["202503", "20250"])


def test_run_live_ingest_gus_months_fetches_cartesian_product(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from younggeul_app_kr_seoul_apartment import pipeline_live
    from younggeul_app_kr_seoul_apartment.connectors.molit import MolitAptRequest

    apt_mock = MagicMock()
    rate_mock = MagicMock()
    apt_mock.return_value.fetch.return_value = ConnectorResult(records=[_apt_record()], manifest=MagicMock())
    rate_mock.return_value.fetch.return_value = ConnectorResult(records=[_rate_record()], manifest=MagicMock())
    monkeypatch.setattr(pipeline_live, "MolitAptConnector", apt_mock)
    monkeypatch.setattr(pipeline_live, "BokInterestRateConnector", rate_mock)
    _kostat_mock = MagicMock()
    _kostat_mock.return_value.fetch.return_value = ConnectorResult(records=[], manifest=MagicMock())
    monkeypatch.setattr(pipeline_live, "KostatMigrationConnector", _kostat_mock)

    client = MagicMock()
    client.dataset.side_effect = lambda _id: MagicMock(spec=Dataset)

    bronze = run_live_ingest_gus_months(client=client, lawd_codes=["11680", "11440"], deal_yms=["202403", "202503"])

    apt_calls = apt_mock.return_value.fetch.call_args_list
    assert len(apt_calls) == 4
    pairs = [(call.args[0].sigungu_code, call.args[0].year_month) for call in apt_calls]
    assert pairs == [
        ("11680", "202403"),
        ("11680", "202503"),
        ("11440", "202403"),
        ("11440", "202503"),
    ]
    for call in apt_calls:
        assert isinstance(call.args[0], MolitAptRequest)

    assert rate_mock.return_value.fetch.call_count == 1
    assert isinstance(bronze, BronzeInput)
    assert len(bronze.apt_transactions) == 4


def test_run_live_ingest_gus_months_rejects_empty_lawd_codes() -> None:
    with pytest.raises(ValueError, match="lawd_codes must not be empty"):
        run_live_ingest_gus_months(client=MagicMock(), lawd_codes=[], deal_yms=["202503"])


def test_run_live_ingest_gus_months_rejects_duplicate_lawd_codes() -> None:
    with pytest.raises(ValueError, match="lawd_codes must not contain duplicates"):
        run_live_ingest_gus_months(client=MagicMock(), lawd_codes=["11680", "11680"], deal_yms=["202503"])


def test_run_live_ingest_gus_months_rejects_invalid_lawd_code() -> None:
    with pytest.raises(ValueError, match="lawd_code must be 5 digits"):
        run_live_ingest_gus_months(client=MagicMock(), lawd_codes=["11680", "1168"], deal_yms=["202503"])



def test_run_live_ingest_emits_kostat_migrations_per_month(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from younggeul_app_kr_seoul_apartment import pipeline_live
    from younggeul_app_kr_seoul_apartment.connectors.kostat import KostatMigrationRequest
    from younggeul_core.state.bronze import BronzeMigration

    apt_mock = MagicMock()
    rate_mock = MagicMock()
    kostat_mock = MagicMock()
    apt_mock.return_value.fetch.return_value = ConnectorResult(records=[_apt_record()], manifest=MagicMock())
    rate_mock.return_value.fetch.return_value = ConnectorResult(records=[_rate_record()], manifest=MagicMock())
    seoul_record = BronzeMigration(
        ingest_timestamp=_NOW,
        source_id="kostat_population_migration",
        raw_response_hash="hash-mig",
        year="2025",
        month="03",
        region_code="11",
        region_name="서울특별시",
        in_count="110859",
        out_count="109553",
        net_count="1306",
    )
    kostat_mock.return_value.fetch.return_value = ConnectorResult(records=[seoul_record], manifest=MagicMock())
    monkeypatch.setattr(pipeline_live, "MolitAptConnector", apt_mock)
    monkeypatch.setattr(pipeline_live, "BokInterestRateConnector", rate_mock)
    monkeypatch.setattr(pipeline_live, "KostatMigrationConnector", kostat_mock)

    client = MagicMock()
    client.dataset.side_effect = lambda _id: MagicMock(spec=Dataset)

    bronze = run_live_ingest_months(
        client=client, lawd_code="11680", deal_yms=["202403", "202503"]
    )

    kostat_calls = kostat_mock.return_value.fetch.call_args_list
    assert len(kostat_calls) == 2
    months = [call.args[0].year_month for call in kostat_calls]
    assert months == ["202403", "202503"]
    for call in kostat_calls:
        assert isinstance(call.args[0], KostatMigrationRequest)
    assert len(bronze.migrations) == 2
    assert bronze.migrations[0].region_code == "11"
