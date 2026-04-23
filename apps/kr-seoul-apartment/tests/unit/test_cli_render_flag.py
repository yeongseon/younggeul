from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

cli = importlib.import_module("younggeul_app_kr_seoul_apartment.cli")


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_simulate_default_render_legacy_writes_markdown_only(runner: CliRunner, tmp_path: Path) -> None:
    output_dir = tmp_path / "simulation"

    result = runner.invoke(
        cli.main,
        ["simulate", "--query", "test", "--max-rounds", "1", "--output-dir", str(output_dir)],
    )

    assert result.exit_code == 0
    assert len(list(output_dir.glob("simulation_report_*.md"))) == 1
    assert list(output_dir.glob("simulation_report_*.json")) == []


def test_simulate_render_abdp_also_writes_json_report(runner: CliRunner, tmp_path: Path) -> None:
    pytest.importorskip("abdp")
    output_dir = tmp_path / "simulation"

    result = runner.invoke(
        cli.main,
        [
            "simulate",
            "--query",
            "test",
            "--max-rounds",
            "1",
            "--output-dir",
            str(output_dir),
            "--render",
            "abdp",
        ],
    )

    assert result.exit_code == 0, result.output
    md_reports = list(output_dir.glob("simulation_report_*.md"))
    json_reports = list(output_dir.glob("simulation_report_*.json"))
    assert len(md_reports) == 1
    assert len(json_reports) == 1
    payload = json.loads(json_reports[0].read_text(encoding="utf-8"))
    assert "markdown" in payload


def test_simulate_render_abdp_json_mode_includes_report_json_file(runner: CliRunner, tmp_path: Path) -> None:
    pytest.importorskip("abdp")
    output_dir = tmp_path / "simulation"

    result = runner.invoke(
        cli.main,
        [
            "--output",
            "json",
            "simulate",
            "--query",
            "test",
            "--max-rounds",
            "1",
            "--output-dir",
            str(output_dir),
            "--render",
            "abdp",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["report_json_file"]
    assert payload["report_json_file"].endswith(".json")


def test_simulate_render_legacy_json_mode_has_null_report_json_file(runner: CliRunner, tmp_path: Path) -> None:
    output_dir = tmp_path / "simulation"

    result = runner.invoke(
        cli.main,
        [
            "--output",
            "json",
            "simulate",
            "--query",
            "test",
            "--max-rounds",
            "1",
            "--output-dir",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["report_json_file"] is None
