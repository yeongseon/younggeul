from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from younggeul_app_kr_seoul_apartment.transforms.gold_enrichment import (
    _pct_change,
    _prev_month,
    _prev_year,
    enrich_district_monthly_trends,
)
from younggeul_core.state.gold import GoldDistrictMonthlyMetrics

_FIXED_NOW = datetime(2026, 3, 29, 12, 0, 0, tzinfo=timezone.utc)


def _make_gold(**overrides: Any) -> GoldDistrictMonthlyMetrics:
    payload: dict[str, Any] = {
        "gu_code": "11680",
        "gu_name": "강남구",
        "period": "2025-07",
        "sale_count": 10,
        "avg_price": 1_000,
        "median_price": 1_000,
        "min_price": 900,
        "max_price": 1_100,
        "price_per_pyeong_avg": 300,
        "yoy_price_change": None,
        "mom_price_change": None,
        "yoy_volume_change": None,
        "mom_volume_change": None,
        "avg_area_m2": Decimal("84.99"),
        "base_interest_rate": Decimal("3.50"),
        "net_migration": 10000,
        "dataset_snapshot_id": f"snapshot-{_FIXED_NOW.date().isoformat()}",
    }
    payload.update(overrides)
    return GoldDistrictMonthlyMetrics(**payload)


class TestPrevMonth:
    def test_normal_month_subtracts_one_month(self) -> None:
        assert _prev_month("2025-07") == "2025-06"

    def test_year_boundary_wraps_to_previous_year_december(self) -> None:
        assert _prev_month("2025-01") == "2024-12"

    def test_double_digit_month_keeps_zero_padding(self) -> None:
        assert _prev_month("2025-10") == "2025-09"

    def test_december_moves_to_november_same_year(self) -> None:
        assert _prev_month("2025-12") == "2025-11"


class TestPrevYear:
    def test_normal_month_subtracts_one_year(self) -> None:
        assert _prev_year("2025-07") == "2024-07"

    def test_january_boundary_subtracts_year_keeps_month(self) -> None:
        assert _prev_year("2024-01") == "2023-01"

    def test_december_subtracts_year_keeps_month(self) -> None:
        assert _prev_year("2025-12") == "2024-12"


class TestPctChange:
    def test_positive_change(self) -> None:
        assert _pct_change(120, 100) == 20.0

    def test_negative_change(self) -> None:
        assert _pct_change(80, 100) == -20.0

    def test_zero_prior_returns_none(self) -> None:
        assert _pct_change(100, 0) is None

    def test_equal_values_return_zero(self) -> None:
        assert _pct_change(100, 100) == 0.0

    def test_float_inputs_are_supported(self) -> None:
        assert _pct_change(1.5, 1.0) == 50.0

    def test_negative_prior_is_computed(self) -> None:
        assert _pct_change(50, -100) == -150.0


class TestEnrichDistrictMonthlyTrends:
    def test_empty_input_returns_empty_list(self) -> None:
        assert enrich_district_monthly_trends([]) == []

    def test_single_month_sets_all_trend_fields_to_none(self) -> None:
        result = enrich_district_monthly_trends([_make_gold(period="2025-07")])

        assert len(result) == 1
        assert result[0].mom_price_change is None
        assert result[0].yoy_price_change is None
        assert result[0].mom_volume_change is None
        assert result[0].yoy_volume_change is None

    def test_two_consecutive_months_populates_mom_only_for_later_month(self) -> None:
        july = _make_gold(period="2025-07", avg_price=1000, sale_count=10)
        august = _make_gold(period="2025-08", avg_price=1100, sale_count=15)

        result = enrich_district_monthly_trends([july, august])
        august_row = next(item for item in result if item.period == "2025-08")

        assert august_row.mom_price_change == 10.0
        assert august_row.mom_volume_change == 50.0
        assert august_row.yoy_price_change is None
        assert august_row.yoy_volume_change is None

    def test_thirteen_months_populates_both_mom_and_yoy(self) -> None:
        metrics = [_make_gold(period=f"2024-{month:02d}", avg_price=1000, sale_count=10) for month in range(8, 13)]
        metrics.extend(_make_gold(period=f"2025-{month:02d}", avg_price=1200, sale_count=12) for month in range(1, 9))

        result = enrich_district_monthly_trends(metrics)
        latest = next(item for item in result if item.period == "2025-08")

        assert latest.mom_price_change == 0.0
        assert latest.yoy_price_change == 20.0
        assert latest.mom_volume_change == 0.0
        assert latest.yoy_volume_change == 20.0

    def test_missing_previous_month_keeps_mom_none(self) -> None:
        may = _make_gold(period="2025-05", avg_price=900, sale_count=9)
        july = _make_gold(period="2025-07", avg_price=1000, sale_count=10)

        result = enrich_district_monthly_trends([may, july])
        july_row = next(item for item in result if item.period == "2025-07")

        assert july_row.mom_price_change is None
        assert july_row.mom_volume_change is None

    def test_missing_previous_year_keeps_yoy_none(self) -> None:
        june = _make_gold(period="2025-06", avg_price=950, sale_count=9)
        july = _make_gold(period="2025-07", avg_price=1000, sale_count=10)

        result = enrich_district_monthly_trends([june, july])
        july_row = next(item for item in result if item.period == "2025-07")

        assert july_row.yoy_price_change is None
        assert july_row.yoy_volume_change is None

    def test_multiple_gu_codes_are_enriched_independently(self) -> None:
        gangnam_july = _make_gold(gu_code="11680", gu_name="강남구", period="2025-07", avg_price=1000, sale_count=10)
        gangnam_aug = _make_gold(gu_code="11680", gu_name="강남구", period="2025-08", avg_price=1200, sale_count=20)
        songpa_aug = _make_gold(gu_code="11710", gu_name="송파구", period="2025-08", avg_price=1300, sale_count=15)

        result = enrich_district_monthly_trends([gangnam_aug, songpa_aug, gangnam_july])
        gangnam_aug_row = next(item for item in result if item.gu_code == "11680" and item.period == "2025-08")
        songpa_aug_row = next(item for item in result if item.gu_code == "11710" and item.period == "2025-08")

        assert gangnam_aug_row.mom_price_change == 20.0
        assert gangnam_aug_row.mom_volume_change == 100.0
        assert songpa_aug_row.mom_price_change is None
        assert songpa_aug_row.mom_volume_change is None

    def test_zero_prior_sale_count_mom_returns_none_for_volume_change(self) -> None:
        july = _make_gold(period="2025-07", sale_count=0)
        august = _make_gold(period="2025-08", sale_count=10)

        result = enrich_district_monthly_trends([july, august])
        august_row = next(item for item in result if item.period == "2025-08")

        assert august_row.mom_volume_change is None

    def test_zero_prior_avg_price_mom_returns_none_for_price_change(self) -> None:
        july = _make_gold(period="2025-07", avg_price=0)
        august = _make_gold(period="2025-08", avg_price=1000)

        result = enrich_district_monthly_trends([july, august])
        august_row = next(item for item in result if item.period == "2025-08")

        assert august_row.mom_price_change is None

    def test_zero_prior_sale_count_yoy_returns_none_for_volume_change(self) -> None:
        prev_year = _make_gold(period="2024-07", sale_count=0)
        current = _make_gold(period="2025-07", sale_count=10)

        result = enrich_district_monthly_trends([current, prev_year])
        current_row = next(item for item in result if item.period == "2025-07")

        assert current_row.yoy_volume_change is None

    def test_zero_prior_avg_price_yoy_returns_none_for_price_change(self) -> None:
        prev_year = _make_gold(period="2024-07", avg_price=0)
        current = _make_gold(period="2025-07", avg_price=1000)

        result = enrich_district_monthly_trends([current, prev_year])
        current_row = next(item for item in result if item.period == "2025-07")

        assert current_row.yoy_price_change is None

    def test_populates_all_four_trend_fields_when_data_exists(self) -> None:
        prev_year = _make_gold(period="2024-07", avg_price=800, sale_count=8)
        prev_month = _make_gold(period="2025-06", avg_price=1000, sale_count=10)
        current = _make_gold(period="2025-07", avg_price=1200, sale_count=12)

        result = enrich_district_monthly_trends([current, prev_year, prev_month])
        current_row = next(item for item in result if item.period == "2025-07")

        assert current_row.mom_price_change == 20.0
        assert current_row.yoy_price_change == 50.0
        assert current_row.mom_volume_change == 20.0
        assert current_row.yoy_volume_change == 50.0

    def test_only_yoy_exists_populates_yoy_and_not_mom(self) -> None:
        prev_year = _make_gold(period="2024-07", avg_price=800, sale_count=8)
        current = _make_gold(period="2025-07", avg_price=1200, sale_count=12)

        result = enrich_district_monthly_trends([current, prev_year])
        current_row = next(item for item in result if item.period == "2025-07")

        assert current_row.mom_price_change is None
        assert current_row.mom_volume_change is None
        assert current_row.yoy_price_change == 50.0
        assert current_row.yoy_volume_change == 50.0

    def test_only_mom_exists_populates_mom_and_not_yoy(self) -> None:
        prev_month = _make_gold(period="2025-06", avg_price=1000, sale_count=10)
        current = _make_gold(period="2025-07", avg_price=1200, sale_count=12)

        result = enrich_district_monthly_trends([current, prev_month])
        current_row = next(item for item in result if item.period == "2025-07")

        assert current_row.mom_price_change == 20.0
        assert current_row.mom_volume_change == 20.0
        assert current_row.yoy_price_change is None
        assert current_row.yoy_volume_change is None

    def test_negative_changes_are_computed_for_price_and_volume(self) -> None:
        prev_month = _make_gold(period="2025-06", avg_price=1000, sale_count=10)
        current = _make_gold(period="2025-07", avg_price=800, sale_count=8)

        result = enrich_district_monthly_trends([prev_month, current])
        current_row = next(item for item in result if item.period == "2025-07")

        assert current_row.mom_price_change == -20.0
        assert current_row.mom_volume_change == -20.0

    def test_input_is_sorted_before_processing(self) -> None:
        row1 = _make_gold(gu_code="11710", gu_name="송파구", period="2025-08")
        row2 = _make_gold(gu_code="11680", gu_name="강남구", period="2025-08")
        row3 = _make_gold(gu_code="11680", gu_name="강남구", period="2025-07")

        result = enrich_district_monthly_trends([row1, row2, row3])

        assert [(item.gu_code, item.period) for item in result] == [
            ("11680", "2025-07"),
            ("11680", "2025-08"),
            ("11710", "2025-08"),
        ]

    def test_returns_new_instances_instead_of_mutating_input(self) -> None:
        july = _make_gold(period="2025-07", avg_price=1000, sale_count=10)
        august = _make_gold(period="2025-08", avg_price=1100, sale_count=11)

        result = enrich_district_monthly_trends([july, august])

        assert result[0] is not july
        assert result[1] is not august
        assert july.mom_price_change is None
        assert august.mom_price_change is None

    def test_non_trend_fields_are_preserved(self) -> None:
        prior = _make_gold(
            period="2025-06",
            avg_area_m2=Decimal("80.00"),
            base_interest_rate=Decimal("3.75"),
            net_migration=123,
            dataset_snapshot_id="snapshot-a",
        )
        current = _make_gold(
            period="2025-07",
            avg_area_m2=Decimal("82.00"),
            base_interest_rate=Decimal("3.50"),
            net_migration=456,
            dataset_snapshot_id="snapshot-b",
        )

        result = enrich_district_monthly_trends([current, prior])
        current_row = next(item for item in result if item.period == "2025-07")

        assert current_row.avg_area_m2 == Decimal("82.00")
        assert current_row.base_interest_rate == Decimal("3.50")
        assert current_row.net_migration == 456
        assert current_row.dataset_snapshot_id == "snapshot-b"
