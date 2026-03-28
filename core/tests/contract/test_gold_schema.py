from decimal import Decimal

import pytest
from pydantic import ValidationError

from core.src.younggeul_core.state.gold import (
    BaselineForecast,
    GoldComplexMonthlyMetrics,
    GoldDistrictMonthlyMetrics,
)


def _district_payload() -> dict[str, object]:
    return {
        "gu_code": "11680",
        "gu_name": "강남구",
        "period": "2026-01",
        "sale_count": 214,
        "avg_price": 1_690_000_000,
        "median_price": 1_580_000_000,
        "min_price": 620_000_000,
        "max_price": 4_350_000_000,
        "price_per_pyeong_avg": 65_000_000,
        "yoy_price_change": 8.4,
        "mom_price_change": 1.2,
        "yoy_volume_change": 5.7,
        "mom_volume_change": -2.1,
        "avg_area_m2": Decimal("82.15"),
        "base_interest_rate": Decimal("3.50"),
        "net_migration": 540,
        "dataset_snapshot_id": "snapshot-2026-01-v1",
    }


def test_gold_district_monthly_metrics_round_trip_all_fields() -> None:
    model = GoldDistrictMonthlyMetrics(**_district_payload())
    restored = GoldDistrictMonthlyMetrics.model_validate(model.model_dump())
    assert restored == model


def test_gold_district_monthly_metrics_core_metrics_defined() -> None:
    model = GoldDistrictMonthlyMetrics(**_district_payload())
    assert model.sale_count == 214
    assert model.avg_price == 1_690_000_000
    assert model.median_price == 1_580_000_000
    assert model.min_price == 620_000_000
    assert model.max_price == 4_350_000_000
    assert model.yoy_price_change == 8.4
    assert model.mom_price_change == 1.2
    assert model.yoy_volume_change == 5.7
    assert model.mom_volume_change == -2.1


def test_gold_complex_monthly_metrics_round_trip() -> None:
    model = GoldComplexMonthlyMetrics(
        complex_id="complex-1168010300-123-45-raemian",
        gu_code="11680",
        period="2026-01",
        sale_count=34,
        avg_price=1_920_000_000,
        median_price=1_880_000_000,
        min_price=1_500_000_000,
        max_price=2_450_000_000,
        price_per_pyeong_avg=71_000_000,
    )
    restored = GoldComplexMonthlyMetrics.model_validate(model.model_dump())
    assert restored == model


@pytest.mark.parametrize("direction", ["up", "down", "flat"])
def test_baseline_forecast_direction_literal_values(direction: str) -> None:
    model = BaselineForecast(
        gu_code="11680",
        gu_name="강남구",
        target_period="2026-02",
        direction=direction,
        direction_confidence=0.78,
        model_name="deterministic_baseline_v1",
    )
    assert model.direction == direction


def test_baseline_forecast_direction_literal_validation() -> None:
    with pytest.raises(ValidationError):
        _ = BaselineForecast(
            gu_code="11680",
            gu_name="강남구",
            target_period="2026-02",
            direction="volatile",
            direction_confidence=0.78,
            model_name="deterministic_baseline_v1",
        )


@pytest.mark.parametrize("confidence", [-0.01, 1.01])
def test_baseline_forecast_direction_confidence_range_validation(confidence: float) -> None:
    with pytest.raises(ValidationError):
        _ = BaselineForecast(
            gu_code="11680",
            gu_name="강남구",
            target_period="2026-02",
            direction="flat",
            direction_confidence=confidence,
            model_name="deterministic_baseline_v1",
        )


def test_gold_district_optional_fields_default_none() -> None:
    model = GoldDistrictMonthlyMetrics(
        gu_code="11680",
        gu_name="강남구",
        period="2026-01",
        sale_count=214,
        avg_price=1_690_000_000,
        median_price=1_580_000_000,
        min_price=620_000_000,
        max_price=4_350_000_000,
        price_per_pyeong_avg=65_000_000,
    )
    assert model.yoy_price_change is None
    assert model.mom_price_change is None
    assert model.yoy_volume_change is None
    assert model.mom_volume_change is None
    assert model.avg_area_m2 is None
    assert model.base_interest_rate is None
    assert model.net_migration is None
    assert model.dataset_snapshot_id is None


@pytest.mark.parametrize(
    ("model_cls", "payload"),
    [
        (GoldDistrictMonthlyMetrics, _district_payload()),
        (
            GoldComplexMonthlyMetrics,
            {
                "complex_id": "complex-1168010300-123-45-raemian",
                "gu_code": "11680",
                "period": "2026-01",
                "sale_count": 34,
                "avg_price": 1_920_000_000,
                "median_price": 1_880_000_000,
                "min_price": 1_500_000_000,
                "max_price": 2_450_000_000,
                "price_per_pyeong_avg": 71_000_000,
            },
        ),
        (
            BaselineForecast,
            {
                "gu_code": "11680",
                "gu_name": "강남구",
                "target_period": "2026-02",
                "direction": "up",
                "direction_confidence": 0.81,
                "predicted_volume": 220,
                "predicted_median_price": 1_610_000_000,
                "model_name": "deterministic_baseline_v1",
                "features_used": ["mom_price_change", "base_interest_rate"],
            },
        ),
    ],
)
def test_json_serialization_round_trip_for_all_gold_models(model_cls: type, payload: dict[str, object]) -> None:
    model = model_cls(**payload)
    restored = model_cls.model_validate_json(model.model_dump_json())
    assert restored == model
