"""Integration test for ``younggeul simulate --shadow-audit-log``.

End-to-end exercise of the abdp shadow runner:

1. Publish a snapshot + baseline.
2. Invoke the CLI with ``--shadow-audit-log <PATH>``.
3. Assert the file was written and parses as a valid JSON document
   carrying the abdp ``AuditLog`` shape (``scenario_key`` versioned,
   ``seed == 0``, non-empty ``run.steps``).

Per Oracle's design ruling D for the shadow-runner work, the synthesized identifiers (Seed,
scenario_key, snapshot UUID, proposal_id) are runner-internal: this test
verifies their *internal* presence in the abdp JSON, never that they
leak into the markdown report.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from click.testing import CliRunner

import younggeul_app_kr_seoul_apartment.cli as cli_module
from younggeul_app_kr_seoul_apartment.forecaster import generate_baseline_report
from younggeul_app_kr_seoul_apartment.snapshot import publish_snapshot
from younggeul_core.state.gold import BaselineForecast, GoldDistrictMonthlyMetrics

pytest.importorskip("abdp")


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
def test_simulate_cli_writes_shadow_audit_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    snapshot_dir = tmp_path / "snap"
    baseline_dir = tmp_path / "baseline"
    output_dir = tmp_path / "sim"
    audit_log_path = tmp_path / "audit.json"

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
            "1",
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
            "--shadow-audit-log",
            str(audit_log_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert audit_log_path.exists(), "shadow audit log file was not written"

    payload = json.loads(audit_log_path.read_text(encoding="utf-8"))

    assert payload["scenario_key"].startswith("yg-scenario-v1:"), payload["scenario_key"]
    assert payload["seed"] == 0
    assert payload["run"]["scenario_key"] == payload["scenario_key"]
    assert payload["run"]["seed"] == 0
    assert isinstance(payload["run"]["steps"], list)
    assert len(payload["run"]["steps"]) >= 1
    assert payload["summary"]["overall_status"] in {"pass", "fail", "warn"}

    markdown = (output_dir / next(iter(p.name for p in output_dir.glob("simulation_report_*.md")))).read_text(
        encoding="utf-8"
    )
    assert "yg-scenario-v1:" not in markdown, "scenario_key must not leak into the markdown report"


@pytest.mark.integration
def test_simulate_cli_rejects_shadow_audit_without_snapshot_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli_module, "validate_max_rounds", lambda _max_rounds: None)
    runner = CliRunner()
    result = runner.invoke(
        cli_module.main,
        [
            "simulate",
            "--query",
            "q",
            "--max-rounds",
            "1",
            "--output-dir",
            str(tmp_path / "out"),
            "--shadow-audit-log",
            str(tmp_path / "audit.json"),
        ],
    )
    assert result.exit_code != 0
    assert "--shadow-audit-log requires --snapshot-dir" in result.output
