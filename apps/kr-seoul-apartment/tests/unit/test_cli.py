from __future__ import annotations

import json
import subprocess
from importlib import import_module
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

cli = import_module("younggeul_app_kr_seoul_apartment.cli")


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_version_outputs_package_version(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "get_runtime_version", lambda: "1.2.3")

    result = runner.invoke(cli.main, ["--version"])

    assert result.exit_code == 0
    assert "1.2.3" in result.output


@pytest.mark.parametrize(
    "args",
    [
        ["--help"],
        ["ingest", "--help"],
        ["snapshot", "--help"],
        ["snapshot", "publish", "--help"],
        ["snapshot", "list", "--help"],
        ["baseline", "--help"],
        ["simulate", "--help"],
        ["report", "--help"],
        ["eval", "--help"],
    ],
)
def test_help_works_for_main_and_commands(runner: CliRunner, args: list[str]) -> None:
    result = runner.invoke(cli.main, args)

    assert result.exit_code == 0
    assert "Usage:" in result.output


def test_ingest_default_creates_output(runner: CliRunner, tmp_path: Path) -> None:
    output_dir = tmp_path / "pipeline"

    result = runner.invoke(cli.main, ["ingest", "--output-dir", str(output_dir)])

    assert result.exit_code == 0
    assert (output_dir / "gold_district_monthly_metrics.jsonl").is_file()


def test_ingest_json_output_is_valid_json(runner: CliRunner, tmp_path: Path) -> None:
    output_dir = tmp_path / "pipeline"

    result = runner.invoke(
        cli.main,
        ["--output", "json", "ingest", "--output-dir", str(output_dir)],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "success"
    assert payload["silver_apt_count"] >= 1
    assert payload["gold_count"] >= 1


def test_ingest_live_requires_gu(runner: CliRunner, tmp_path: Path) -> None:
    result = runner.invoke(
        cli.main,
        [
            "ingest",
            "--source",
            "live",
            "--month",
            "202503",
            "--output-dir",
            str(tmp_path),
        ],
    )

    assert result.exit_code != 0
    assert "exactly one of --gu or --gus" in result.output


def test_ingest_live_requires_month_or_months(runner: CliRunner, tmp_path: Path) -> None:
    result = runner.invoke(
        cli.main,
        ["ingest", "--source", "live", "--gu", "11680", "--output-dir", str(tmp_path)],
    )

    assert result.exit_code != 0
    assert "exactly one of --month or --months" in result.output


def test_ingest_live_rejects_month_and_months_together(runner: CliRunner, tmp_path: Path) -> None:
    result = runner.invoke(
        cli.main,
        [
            "ingest",
            "--source",
            "live",
            "--gu",
            "11680",
            "--month",
            "202503",
            "--months",
            "202403,202503",
            "--output-dir",
            str(tmp_path),
        ],
    )

    assert result.exit_code != 0
    assert "mutually exclusive" in result.output


def test_ingest_live_rejects_gu_and_gus_together(runner: CliRunner, tmp_path: Path) -> None:
    result = runner.invoke(
        cli.main,
        [
            "ingest",
            "--source",
            "live",
            "--gu",
            "11680",
            "--gus",
            "11680,11440",
            "--month",
            "202503",
            "--output-dir",
            str(tmp_path),
        ],
    )

    assert result.exit_code != 0
    assert "--gu and --gus are mutually exclusive" in result.output


def test_simulate_runs_successfully(runner: CliRunner, tmp_path: Path) -> None:
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
        ],
    )

    assert result.exit_code == 0
    reports = list(output_dir.glob("simulation_report_*.md"))
    assert len(reports) == 1
    assert reports[0].read_text(encoding="utf-8").startswith("# Simulation Report")


def test_simulate_json_output_is_valid_json(runner: CliRunner, tmp_path: Path) -> None:
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

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["run_id"]
    assert payload["rendered_report"]["markdown"].startswith("# Simulation Report")


def test_simulate_passes_model_id_to_graph_seed(
    runner: CliRunner,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}
    original_seed_graph_state = cli.seed_graph_state

    class FakeGraph:
        def invoke(self, initial_state: dict[str, Any]) -> dict[str, Any]:
            return {
                **initial_state,
                "round_no": 1,
                "event_refs": [],
                "warnings": [],
            }

    class FakeRenderedReport:
        markdown = "# Simulation Report\n\nstub"

        def model_dump(self, mode: str = "python") -> dict[str, Any]:
            _ = mode
            return {"markdown": self.markdown}

    def fake_seed_graph_state(query: str, *, run_id: str, run_name: str, model_id: str) -> dict[str, Any]:
        captured["model_id"] = model_id
        return original_seed_graph_state(query, run_id=run_id, run_name=run_name, model_id=model_id)

    monkeypatch.setattr(cli, "seed_graph_state", fake_seed_graph_state)
    monkeypatch.setattr(cli, "build_simulation_graph", lambda *args, **kwargs: FakeGraph())
    monkeypatch.setattr(cli, "_extract_rendered_report", lambda *args, **kwargs: FakeRenderedReport())

    result = runner.invoke(
        cli.main,
        [
            "simulate",
            "--query",
            "test",
            "--max-rounds",
            "1",
            "--model-id",
            "gpt-4o-mini",
            "--output-dir",
            str(tmp_path / "simulation"),
        ],
    )

    assert result.exit_code == 0
    assert captured["model_id"] == "gpt-4o-mini"


def test_simulate_rejects_invalid_model_id(runner: CliRunner, tmp_path: Path) -> None:
    result = runner.invoke(
        cli.main,
        [
            "simulate",
            "--query",
            "test",
            "--model-id",
            "not-allowed",
            "--output-dir",
            str(tmp_path / "simulation"),
        ],
    )

    assert result.exit_code != 0
    assert "model_id 'not-allowed' is not allowed" in result.output
    assert "Fatal error:" not in result.output


def test_eval_invokes_subprocess_and_returns_success(
    runner: CliRunner,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        command: list[str] = list(args[0])
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="eval ok\n", stderr="")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    output_dir = tmp_path / "eval"

    result = runner.invoke(cli.main, ["eval", "--output-dir", str(output_dir)])

    assert result.exit_code == 0
    assert calls
    assert "-m" in calls[0]
    assert (output_dir / "eval_summary.json").is_file()


def test_snapshot_list_with_empty_directory(runner: CliRunner, tmp_path: Path) -> None:
    snapshot_dir = tmp_path / "snapshots"

    result = runner.invoke(cli.main, ["snapshot", "list", "--snapshot-dir", str(snapshot_dir)])

    assert result.exit_code == 0
    assert "No snapshots found" in result.output


def test_baseline_with_missing_snapshot_returns_error(runner: CliRunner, tmp_path: Path) -> None:
    result = runner.invoke(
        cli.main,
        [
            "baseline",
            "--snapshot-id",
            "latest",
            "--snapshot-dir",
            str(tmp_path / "missing"),
        ],
    )

    assert result.exit_code != 0
    assert "Error:" in result.output


def test_report_nonexistent_file_returns_error(runner: CliRunner, tmp_path: Path) -> None:
    result = runner.invoke(
        cli.main,
        ["report", "--report-file", str(tmp_path / "not-found.md")],
    )

    assert result.exit_code != 0
    assert "Report file not found" in result.output
