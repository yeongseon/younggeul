from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from click.testing import CliRunner

import younggeul_app_kr_seoul_apartment.cli as cli_module
from younggeul_app_kr_seoul_apartment.forecaster import generate_baseline_report
from younggeul_app_kr_seoul_apartment.snapshot import publish_snapshot
from younggeul_core.state.gold import BaselineForecast, GoldDistrictMonthlyMetrics


def _make_metric(*, period: str, sale_count: int, median_price: int) -> GoldDistrictMonthlyMetrics:
    return GoldDistrictMonthlyMetrics(
        gu_code="11680",
        gu_name="강남구",
        period=period,
        sale_count=sale_count,
        avg_price=median_price,
        median_price=median_price,
        min_price=median_price - 100_000_000,
        max_price=median_price + 100_000_000,
        price_per_pyeong_avg=1000,
        yoy_price_change=5.0,
        mom_price_change=2.0,
        yoy_volume_change=1.0,
        mom_volume_change=1.0,
        avg_area_m2=Decimal("84.5"),
        base_interest_rate=Decimal("3.50"),
        net_migration=120,
    )


@pytest.mark.integration
def test_simulate_cli_uses_live_snapshot_metrics(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    snapshot_dir = tmp_path / "snap-25"
    baseline_dir = tmp_path / "baseline-25"
    output_dir = tmp_path / "sim-live"
    snapshot_ref = publish_snapshot(
        [
            _make_metric(period="2024-03", sale_count=40, median_price=2_100_000_000),
            _make_metric(period="2025-03", sale_count=89, median_price=2_700_000_000),
        ],
        snapshot_dir,
    )
    generate_baseline_report(
        snapshot_ref,
        [
            BaselineForecast(
                gu_code="11680",
                gu_name="강남구",
                target_period="2025-04",
                direction="up",
                direction_confidence=0.8,
                predicted_volume=95,
                predicted_median_price=2_800_000_000,
                model_name="momentum_v1",
                features_used=["mom_price_change"],
            )
        ],
        baseline_dir,
    )

    monkeypatch.setattr(cli_module, "validate_max_rounds", lambda _max_rounds: None)
    runner = CliRunner()
    result = runner.invoke(
        cli_module.main,
        [
            "simulate",
            "--query",
            "서울 강남구 아파트 시장 전망",
            "--max-rounds",
            "0",
            "--snapshot-dir",
            str(snapshot_dir),
            "--baseline-dir",
            str(baseline_dir),
            "--gus",
            "11680",
            "--output-dir",
            str(output_dir),
            "--model-id",
            "stub",
        ],
    )

    assert result.exit_code == 0, result.output
    reports = list(output_dir.glob("simulation_report_*.md"))
    assert len(reports) == 1

    markdown = reports[0].read_text(encoding="utf-8")
    assert "강남구(11680) trading volume is 89 with median price 2700000000 at round 0." in markdown
    assert "median price 2000000" not in markdown
