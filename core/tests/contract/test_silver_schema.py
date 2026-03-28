from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from core.src.younggeul_core.state.silver import (
    SilverAptTransaction,
    SilverComplexBridge,
    SilverDataQualityScore,
    SilverInterestRate,
    SilverMigration,
)


def _ingest_timestamp() -> datetime:
    return datetime(2026, 2, 1, 10, 20, 30, tzinfo=timezone.utc)


def _quality_score() -> SilverDataQualityScore:
    return SilverDataQualityScore(completeness=98.2, consistency=96.5, overall=97.6)


def _silver_apt_payload() -> dict[str, object]:
    return {
        "transaction_id": "tx-1168010300-123-45-2026-01-15-1200000000",
        "deal_amount": 1_200_000_000,
        "deal_date": date(2026, 1, 15),
        "build_year": 2016,
        "dong_code": "1168010300",
        "dong_name": "역삼동",
        "gu_code": "11680",
        "gu_name": "강남구",
        "apt_name": "래미안",
        "floor": 12,
        "area_exclusive_m2": Decimal("84.99"),
        "jibun": "123-45",
        "road_name": "테헤란로",
        "is_cancelled": False,
        "cancel_date": None,
        "deal_type": "중개거래",
        "source_id": "molit_apt_trade_v2",
        "ingest_timestamp": _ingest_timestamp(),
        "quality_score": _quality_score(),
    }


def test_silver_apt_transaction_round_trip_all_fields_populated() -> None:
    model = SilverAptTransaction(**_silver_apt_payload())
    restored = SilverAptTransaction.model_validate(model.model_dump())
    assert restored == model


def test_silver_apt_transaction_deal_amount_is_int_krw() -> None:
    model = SilverAptTransaction(**_silver_apt_payload())
    assert isinstance(model.deal_amount, int)
    assert model.deal_amount == 1_200_000_000


def test_silver_apt_transaction_deal_date_is_date() -> None:
    model = SilverAptTransaction(**_silver_apt_payload())
    assert isinstance(model.deal_date, date)


def test_silver_apt_transaction_area_is_decimal() -> None:
    model = SilverAptTransaction(**_silver_apt_payload())
    assert isinstance(model.area_exclusive_m2, Decimal)
    assert model.area_exclusive_m2 == Decimal("84.99")


@pytest.mark.parametrize("score", [-0.1, 100.1])
def test_silver_data_quality_score_range_validation(score: float) -> None:
    with pytest.raises(ValidationError):
        _ = SilverDataQualityScore(completeness=score, consistency=90.0, overall=90.0)


def test_silver_interest_rate_round_trip_and_decimal_rate() -> None:
    model = SilverInterestRate(
        rate_date=date(2026, 1, 1),
        rate_type="base_rate",
        rate_value=Decimal("3.50"),
        source_id="bank_of_korea_base_rate",
        ingest_timestamp=_ingest_timestamp(),
    )
    restored = SilverInterestRate.model_validate(model.model_dump())
    assert restored == model
    assert isinstance(restored.rate_value, Decimal)


def test_silver_migration_round_trip_and_int_counts() -> None:
    model = SilverMigration(
        period="2026-01",
        region_code="11680",
        region_name="강남구",
        in_count=4520,
        out_count=3980,
        net_count=540,
        source_id="kosis_migration_monthly",
        ingest_timestamp=_ingest_timestamp(),
    )
    restored = SilverMigration.model_validate(model.model_dump())
    assert restored == model
    assert isinstance(restored.in_count, int)
    assert isinstance(restored.out_count, int)
    assert isinstance(restored.net_count, int)


def test_silver_complex_bridge_round_trip() -> None:
    model = SilverComplexBridge(
        complex_id="complex-1168010300-123-45-raemian",
        dong_code="1168010300",
        jibun="123-45",
        road_name="테헤란로",
        apt_name="래미안",
        build_year=2016,
        matched_at=_ingest_timestamp(),
        match_method="jibun_match",
    )
    restored = SilverComplexBridge.model_validate(model.model_dump())
    assert restored == model


def test_silver_complex_bridge_match_method_literal_validation() -> None:
    with pytest.raises(ValidationError):
        _ = SilverComplexBridge(
            complex_id="complex-1",
            dong_code="1168010300",
            apt_name="래미안",
            matched_at=_ingest_timestamp(),
            match_method="fuzzy",
        )


@pytest.mark.parametrize(
    ("model_cls", "payload"),
    [
        (
            SilverDataQualityScore,
            {"completeness": 98.2, "consistency": 96.5, "overall": 97.6},
        ),
        (SilverAptTransaction, _silver_apt_payload()),
        (
            SilverInterestRate,
            {
                "rate_date": date(2026, 1, 1),
                "rate_type": "base_rate",
                "rate_value": Decimal("3.50"),
                "source_id": "bank_of_korea_base_rate",
                "ingest_timestamp": _ingest_timestamp(),
            },
        ),
        (
            SilverMigration,
            {
                "period": "2026-01",
                "region_code": "11680",
                "region_name": "강남구",
                "in_count": 4520,
                "out_count": 3980,
                "net_count": 540,
                "source_id": "kosis_migration_monthly",
                "ingest_timestamp": _ingest_timestamp(),
            },
        ),
        (
            SilverComplexBridge,
            {
                "complex_id": "complex-1168010300-123-45-raemian",
                "dong_code": "1168010300",
                "jibun": "123-45",
                "road_name": "테헤란로",
                "apt_name": "래미안",
                "build_year": 2016,
                "matched_at": _ingest_timestamp(),
                "match_method": "exact_code",
            },
        ),
    ],
)
def test_json_serialization_round_trip_for_all_silver_models(model_cls: type, payload: dict[str, object]) -> None:
    model = model_cls(**payload)
    restored = model_cls.model_validate_json(model.model_dump_json())
    assert restored == model
