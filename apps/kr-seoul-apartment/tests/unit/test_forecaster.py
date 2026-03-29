from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from younggeul_app_kr_seoul_apartment.forecaster import (
    _next_period,
    forecast_baseline,
    generate_baseline_report,
)
from younggeul_core.state.gold import BaselineForecast, GoldDistrictMonthlyMetrics
from younggeul_core.state.simulation import SnapshotRef


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
        "dataset_snapshot_id": "a" * 64,
    }
    payload.update(overrides)
    return GoldDistrictMonthlyMetrics(**payload)


def _make_snapshot_ref(**overrides: Any) -> SnapshotRef:
    payload: dict[str, Any] = {
        "dataset_snapshot_id": "b" * 64,
        "created_at": datetime(2026, 3, 29, 12, 0, 0, tzinfo=timezone.utc),
        "table_count": 1,
    }
    payload.update(overrides)
    return SnapshotRef(**payload)


def _make_forecast(**overrides: Any) -> BaselineForecast:
    payload: dict[str, Any] = {
        "gu_code": "11680",
        "gu_name": "강남구",
        "target_period": "2025-08",
        "direction": "flat",
        "direction_confidence": 0.4,
        "predicted_volume": 10,
        "predicted_median_price": 1000,
        "model_name": "momentum_v1",
        "features_used": ["mom_price_change"],
    }
    payload.update(overrides)
    return BaselineForecast(**payload)


class TestNextPeriod:
    def test_normal_month_increment(self) -> None:
        assert _next_period("2025-07") == "2025-08"

    def test_december_wraps_to_january_of_next_year(self) -> None:
        assert _next_period("2025-12") == "2026-01"

    def test_zero_padding_is_preserved(self) -> None:
        assert _next_period("2025-09") == "2025-10"


class TestForecastBaseline:
    def test_single_gu_strong_upward_trend_is_up(self) -> None:
        metrics = [
            _make_gold(period="2025-05", avg_price=1000),
            _make_gold(period="2025-06", avg_price=1000),
            _make_gold(period="2025-07", avg_price=1200, mom_price_change=6.0, mom_volume_change=2.0),
        ]

        result = forecast_baseline(metrics)

        assert len(result) == 1
        assert result[0].direction == "up"

    def test_single_gu_strong_downward_trend_is_down(self) -> None:
        metrics = [
            _make_gold(period="2025-05", avg_price=1200),
            _make_gold(period="2025-06", avg_price=1100),
            _make_gold(period="2025-07", avg_price=900, mom_price_change=-5.0, mom_volume_change=-3.0),
        ]

        result = forecast_baseline(metrics)

        assert len(result) == 1
        assert result[0].direction == "down"

    def test_single_gu_near_zero_momentum_is_flat(self) -> None:
        metrics = [
            _make_gold(period="2025-05", avg_price=1000),
            _make_gold(period="2025-06", avg_price=1000),
            _make_gold(period="2025-07", avg_price=1000, mom_price_change=0.0, mom_volume_change=0.0),
        ]

        result = forecast_baseline(metrics)

        assert result[0].direction == "flat"

    def test_multiple_gus_produce_forecast_per_gu(self) -> None:
        metrics = [
            _make_gold(gu_code="11710", gu_name="송파구", period="2025-07", mom_price_change=2.0),
            _make_gold(gu_code="11680", gu_name="강남구", period="2025-07", mom_price_change=2.0),
        ]

        result = forecast_baseline(metrics)

        assert len(result) == 2
        assert [item.gu_code for item in result] == ["11680", "11710"]

    def test_empty_input_returns_empty_output(self) -> None:
        assert forecast_baseline([]) == []

    def test_single_month_no_mom_available_is_flat_with_low_confidence(self) -> None:
        result = forecast_baseline([_make_gold(period="2025-07")])

        assert result[0].direction == "flat"
        assert result[0].direction_confidence == 0.2

    def test_exactly_three_months_computes_ma3_signal(self) -> None:
        metrics = [
            _make_gold(period="2025-05", avg_price=100),
            _make_gold(period="2025-06", avg_price=100),
            _make_gold(period="2025-07", avg_price=130, mom_price_change=0.0, mom_volume_change=0.0),
        ]

        result = forecast_baseline(metrics)

        assert result[0].direction == "up"

    def test_twelve_or_more_months_sets_high_confidence(self) -> None:
        metrics = [_make_gold(period=f"2025-{month:02d}") for month in range(1, 13)]

        result = forecast_baseline(metrics)

        assert result[0].direction_confidence == 0.8

    def test_six_months_sets_medium_confidence(self) -> None:
        metrics = [_make_gold(period=f"2025-{month:02d}") for month in range(1, 7)]

        result = forecast_baseline(metrics)

        assert result[0].direction_confidence == 0.6

    def test_three_months_sets_low_medium_confidence(self) -> None:
        metrics = [_make_gold(period=f"2025-{month:02d}") for month in range(5, 8)]

        result = forecast_baseline(metrics)

        assert result[0].direction_confidence == 0.4

    def test_less_than_three_months_sets_lowest_confidence(self) -> None:
        metrics = [_make_gold(period="2025-06"), _make_gold(period="2025-07")]

        result = forecast_baseline(metrics)

        assert result[0].direction_confidence == 0.2

    def test_predicted_median_price_uses_mom_price_change(self) -> None:
        metrics = [_make_gold(period="2025-07", median_price=2000, mom_price_change=10.0)]

        result = forecast_baseline(metrics)

        assert result[0].predicted_median_price == 2200

    def test_predicted_median_price_falls_back_when_mom_missing(self) -> None:
        metrics = [_make_gold(period="2025-07", median_price=2100, mom_price_change=None)]

        result = forecast_baseline(metrics)

        assert result[0].predicted_median_price == 2100

    def test_predicted_volume_never_goes_below_zero(self) -> None:
        metrics = [_make_gold(period="2025-07", sale_count=10, mom_volume_change=-250.0)]

        result = forecast_baseline(metrics)

        assert result[0].predicted_volume == 0

    def test_predicted_volume_falls_back_when_mom_missing(self) -> None:
        metrics = [_make_gold(period="2025-07", sale_count=77, mom_volume_change=None)]

        result = forecast_baseline(metrics)

        assert result[0].predicted_volume == 77

    def test_features_used_only_includes_non_none_latest_fields(self) -> None:
        metrics = [
            _make_gold(
                period="2025-07",
                mom_price_change=1.0,
                yoy_price_change=None,
                mom_volume_change=2.0,
                yoy_volume_change=None,
                base_interest_rate=Decimal("3.25"),
                net_migration=None,
            )
        ]

        result = forecast_baseline(metrics)

        assert result[0].features_used == [
            "mom_price_change",
            "mom_volume_change",
            "base_interest_rate",
        ]

    def test_target_period_is_next_month_from_latest(self) -> None:
        metrics = [_make_gold(period="2025-12")]

        result = forecast_baseline(metrics)

        assert result[0].target_period == "2026-01"

    def test_model_name_is_momentum_v1(self) -> None:
        result = forecast_baseline([_make_gold(period="2025-07")])

        assert result[0].model_name == "momentum_v1"

    def test_unsorted_rows_for_same_gu_are_sorted_by_period(self) -> None:
        metrics = [
            _make_gold(period="2025-08", median_price=1000, mom_price_change=10.0),
            _make_gold(period="2025-06", median_price=800, mom_price_change=1.0),
            _make_gold(period="2025-07", median_price=900, mom_price_change=2.0),
        ]

        result = forecast_baseline(metrics)

        assert result[0].target_period == "2025-09"
        assert result[0].predicted_median_price == 1100

    def test_score_exactly_positive_one_is_flat(self) -> None:
        metrics = [
            _make_gold(period="2025-06", avg_price=1000),
            _make_gold(period="2025-07", avg_price=1000, mom_price_change=1.0, mom_volume_change=4.0),
        ]

        result = forecast_baseline(metrics)

        assert result[0].direction == "flat"

    def test_score_exactly_negative_one_is_flat(self) -> None:
        metrics = [
            _make_gold(period="2025-06", avg_price=1000),
            _make_gold(period="2025-07", avg_price=1000, mom_price_change=-1.0, mom_volume_change=-4.0),
        ]

        result = forecast_baseline(metrics)

        assert result[0].direction == "flat"

    def test_fewer_than_three_rows_use_all_rows_for_ma_signal(self) -> None:
        metrics = [
            _make_gold(period="2025-06", avg_price=100),
            _make_gold(period="2025-07", avg_price=150, mom_price_change=0.0, mom_volume_change=0.0),
        ]

        result = forecast_baseline(metrics)

        assert result[0].direction == "up"

    def test_latest_row_gu_name_is_used(self) -> None:
        metrics = [
            _make_gold(period="2025-06", gu_name="강남구(구)", mom_price_change=0.0),
            _make_gold(period="2025-07", gu_name="강남구", mom_price_change=0.0),
        ]

        result = forecast_baseline(metrics)

        assert result[0].gu_name == "강남구"


class TestGenerateBaselineReport:
    def test_creates_report_file_at_expected_path(self, tmp_path: Path) -> None:
        snapshot = _make_snapshot_ref(dataset_snapshot_id="c" * 64)

        path = generate_baseline_report(snapshot, [_make_forecast()], tmp_path)

        assert path == tmp_path / "baseline_report_cccccccccccc.json"
        assert path.is_file()

    def test_output_dir_is_created_if_missing(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "nested" / "reports"

        path = generate_baseline_report(_make_snapshot_ref(), [_make_forecast()], output_dir)

        assert output_dir.is_dir()
        assert path.is_file()

    def test_report_json_structure_matches_spec(self, tmp_path: Path) -> None:
        snapshot = _make_snapshot_ref()
        forecasts = [_make_forecast()]

        report_path = generate_baseline_report(snapshot, forecasts, tmp_path)
        payload = json.loads(report_path.read_text(encoding="utf-8"))

        assert set(payload.keys()) == {
            "report_type",
            "generated_at",
            "snapshot",
            "summary",
            "forecasts",
        }
        assert set(payload["snapshot"].keys()) == {
            "dataset_snapshot_id",
            "created_at",
            "table_count",
        }
        assert set(payload["summary"].keys()) == {
            "total_districts",
            "direction_counts",
            "avg_confidence",
        }

    def test_direction_counts_sum_correctly(self, tmp_path: Path) -> None:
        forecasts = [
            _make_forecast(direction="up"),
            _make_forecast(gu_code="11710", direction="down"),
            _make_forecast(gu_code="11470", direction="flat"),
            _make_forecast(gu_code="11500", direction="up"),
        ]

        report_path = generate_baseline_report(_make_snapshot_ref(), forecasts, tmp_path)
        payload = json.loads(report_path.read_text(encoding="utf-8"))

        counts = payload["summary"]["direction_counts"]
        assert counts == {"up": 2, "down": 1, "flat": 1}
        assert sum(counts.values()) == payload["summary"]["total_districts"]

    def test_avg_confidence_is_rounded_to_two_decimals(self, tmp_path: Path) -> None:
        forecasts = [
            _make_forecast(direction_confidence=0.4),
            _make_forecast(gu_code="11710", direction_confidence=0.8),
            _make_forecast(gu_code="11470", direction_confidence=0.6),
        ]

        report_path = generate_baseline_report(_make_snapshot_ref(), forecasts, tmp_path)
        payload = json.loads(report_path.read_text(encoding="utf-8"))

        assert payload["summary"]["avg_confidence"] == 0.6

    def test_empty_forecasts_produces_valid_zero_summary(self, tmp_path: Path) -> None:
        report_path = generate_baseline_report(_make_snapshot_ref(), [], tmp_path)
        payload = json.loads(report_path.read_text(encoding="utf-8"))

        assert payload["summary"]["total_districts"] == 0
        assert payload["summary"]["direction_counts"] == {"up": 0, "down": 0, "flat": 0}
        assert payload["summary"]["avg_confidence"] == 0.0
        assert payload["forecasts"] == []

    def test_forecasts_serialized_from_model_dump(self, tmp_path: Path) -> None:
        forecast = _make_forecast(features_used=["mom_price_change", "base_interest_rate"])

        report_path = generate_baseline_report(_make_snapshot_ref(), [forecast], tmp_path)
        payload = json.loads(report_path.read_text(encoding="utf-8"))

        assert payload["forecasts"][0] == forecast.model_dump()

    def test_snapshot_metadata_is_preserved(self, tmp_path: Path) -> None:
        snapshot = _make_snapshot_ref(
            dataset_snapshot_id="d" * 64,
            created_at=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            table_count=3,
        )

        report_path = generate_baseline_report(snapshot, [_make_forecast()], tmp_path)
        payload = json.loads(report_path.read_text(encoding="utf-8"))

        assert payload["snapshot"]["dataset_snapshot_id"] == "d" * 64
        assert payload["snapshot"]["created_at"] == "2026-01-01T00:00:00+00:00"
        assert payload["snapshot"]["table_count"] == 3

    def test_report_type_is_baseline_forecast(self, tmp_path: Path) -> None:
        report_path = generate_baseline_report(_make_snapshot_ref(), [_make_forecast()], tmp_path)
        payload = json.loads(report_path.read_text(encoding="utf-8"))

        assert payload["report_type"] == "baseline_forecast"

    def test_generated_at_is_iso_timestamp(self, tmp_path: Path) -> None:
        report_path = generate_baseline_report(_make_snapshot_ref(), [_make_forecast()], tmp_path)
        payload = json.loads(report_path.read_text(encoding="utf-8"))

        generated_at = datetime.fromisoformat(payload["generated_at"])
        assert generated_at.tzinfo is not None
