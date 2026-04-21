from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from younggeul_app_kr_seoul_apartment.simulation.adapters.filesystem_snapshot_reader import (
    FilesystemSnapshotReader,
)
from younggeul_core.state.gold import BaselineForecast, GoldDistrictMonthlyMetrics
from younggeul_core.state.simulation import SnapshotRef
from younggeul_core.storage.snapshot import SnapshotManifest, SnapshotTableEntry


def _make_metric(
    *,
    gu_code: str,
    gu_name: str,
    period: str,
    sale_count: int,
    median_price: int,
) -> GoldDistrictMonthlyMetrics:
    return GoldDistrictMonthlyMetrics(
        gu_code=gu_code,
        gu_name=gu_name,
        period=period,
        sale_count=sale_count,
        avg_price=median_price,
        median_price=median_price,
        min_price=median_price - 100_000_000,
        max_price=median_price + 100_000_000,
        price_per_pyeong_avg=1000,
        yoy_price_change=1.0,
        mom_price_change=0.5,
        yoy_volume_change=0.1,
        mom_volume_change=0.2,
        avg_area_m2=Decimal("84.5"),
        base_interest_rate=Decimal("3.50"),
        net_migration=100,
        dataset_snapshot_id=None,
    )


def _make_forecast(*, gu_code: str, gu_name: str, predicted_median_price: int) -> BaselineForecast:
    return BaselineForecast(
        gu_code=gu_code,
        gu_name=gu_name,
        target_period="2025-04",
        direction="up",
        direction_confidence=0.8,
        predicted_volume=100,
        predicted_median_price=predicted_median_price,
        model_name="momentum_v1",
        features_used=["mom_price_change"],
    )


def _write_snapshot(snapshot_dir: Path, metrics: list[GoldDistrictMonthlyMetrics]) -> SnapshotRef:
    snapshot_id = "a" * 64
    target_dir = snapshot_dir / snapshot_id
    target_dir.mkdir(parents=True)
    table_path = target_dir / "gold_district_monthly_metrics.jsonl"
    payload = "\n".join(metric.model_dump_json() for metric in metrics) + "\n"
    table_path.write_text(payload, encoding="utf-8")

    manifest = SnapshotManifest(
        dataset_snapshot_id=snapshot_id,
        created_at=datetime(2025, 3, 15, tzinfo=timezone.utc),
        table_entries=[
            SnapshotTableEntry(
                table_name="gold_district_monthly_metrics",
                table_hash="0" * 64,
                record_count=len(metrics),
                schema_version="1.0.0",
                file_format="jsonl",
            )
        ],
    )
    manifest_path = target_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest.model_dump(mode="json")), encoding="utf-8")
    return SnapshotRef(
        dataset_snapshot_id=snapshot_id,
        created_at=manifest.created_at,
        table_count=len(manifest.table_entries),
    )


def _write_baseline_report(
    baseline_dir: Path,
    snapshot: SnapshotRef,
    forecasts: list[BaselineForecast],
    *,
    suffix: str,
) -> None:
    baseline_dir.mkdir(parents=True, exist_ok=True)
    report_path = baseline_dir / f"baseline_report_{suffix}.json"
    report_path.write_text(
        json.dumps(
            {
                "snapshot": snapshot.model_dump(mode="json"),
                "forecasts": [forecast.model_dump(mode="json") for forecast in forecasts],
            }
        ),
        encoding="utf-8",
    )


def test_get_coverage_reads_manifest_and_jsonl(tmp_path: Path) -> None:
    snapshot_dir = tmp_path / "snapshots"
    snapshot = _write_snapshot(
        snapshot_dir,
        [
            _make_metric(gu_code="11440", gu_name="마포구", period="2024-03", sale_count=20, median_price=900_000_000),
            _make_metric(
                gu_code="11680", gu_name="강남구", period="2025-03", sale_count=89, median_price=2_700_000_000
            ),
            _make_metric(gu_code="11440", gu_name="마포구", period="2025-03", sale_count=22, median_price=950_000_000),
        ],
    )

    reader = FilesystemSnapshotReader(snapshot_dir)
    coverage = reader.get_coverage(snapshot)

    assert coverage.available_gu_codes == ["11440", "11680"]
    assert coverage.available_gu_names == {"11440": "마포구", "11680": "강남구"}
    assert coverage.min_period == "2024-03"
    assert coverage.max_period == "2025-03"
    assert coverage.record_count == 3


def test_get_latest_metrics_returns_latest_rows_and_filters_by_gu(tmp_path: Path) -> None:
    snapshot_dir = tmp_path / "snapshots"
    snapshot = _write_snapshot(
        snapshot_dir,
        [
            _make_metric(
                gu_code="11680", gu_name="강남구", period="2024-03", sale_count=50, median_price=2_100_000_000
            ),
            _make_metric(
                gu_code="11680", gu_name="강남구", period="2025-03", sale_count=89, median_price=2_700_000_000
            ),
            _make_metric(gu_code="11440", gu_name="마포구", period="2025-03", sale_count=22, median_price=950_000_000),
        ],
    )

    reader = FilesystemSnapshotReader(snapshot_dir)

    latest_metrics = reader.get_latest_metrics(snapshot, ["11680", "11440"])
    gangnam_only = reader.get_latest_metrics(snapshot, ["11680"])

    assert [(metric.gu_code, metric.period, metric.median_price) for metric in latest_metrics] == [
        ("11440", "2025-03", 950_000_000),
        ("11680", "2025-03", 2_700_000_000),
    ]
    assert [(metric.gu_code, metric.sale_count, metric.median_price) for metric in gangnam_only] == [
        ("11680", 89, 2_700_000_000)
    ]


def test_get_baseline_forecasts_returns_empty_without_baseline_dir(tmp_path: Path) -> None:
    snapshot_dir = tmp_path / "snapshots"
    snapshot = _write_snapshot(
        snapshot_dir,
        [_make_metric(gu_code="11680", gu_name="강남구", period="2025-03", sale_count=89, median_price=2_700_000_000)],
    )

    reader = FilesystemSnapshotReader(snapshot_dir)

    assert reader.get_baseline_forecasts(snapshot) == []


def test_get_baseline_forecasts_filters_multiple_gu_codes(tmp_path: Path) -> None:
    snapshot_dir = tmp_path / "snapshots"
    baseline_dir = tmp_path / "baseline"
    snapshot = _write_snapshot(
        snapshot_dir,
        [
            _make_metric(
                gu_code="11680", gu_name="강남구", period="2025-03", sale_count=89, median_price=2_700_000_000
            ),
            _make_metric(gu_code="11440", gu_name="마포구", period="2025-03", sale_count=22, median_price=950_000_000),
        ],
    )
    _write_baseline_report(
        baseline_dir,
        snapshot,
        [
            _make_forecast(gu_code="11680", gu_name="강남구", predicted_median_price=2_800_000_000),
            _make_forecast(gu_code="11440", gu_name="마포구", predicted_median_price=980_000_000),
        ],
        suffix="one",
    )

    reader = FilesystemSnapshotReader(snapshot_dir, baseline_dir)
    forecasts = reader.get_baseline_forecasts(snapshot, ["11680", "11440"])
    gangnam_only = reader.get_baseline_forecasts(snapshot, ["11680"])

    assert [(forecast.gu_code, forecast.predicted_median_price) for forecast in forecasts] == [
        ("11680", 2_800_000_000),
        ("11440", 980_000_000),
    ]
    assert [(forecast.gu_code, forecast.predicted_median_price) for forecast in gangnam_only] == [
        ("11680", 2_800_000_000)
    ]
