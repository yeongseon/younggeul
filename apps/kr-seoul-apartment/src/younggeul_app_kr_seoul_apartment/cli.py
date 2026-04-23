"""CLI entrypoints for ingest, snapshot, baseline, and simulation workflows."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import click
from pydantic import ValidationError

from younggeul_core.state.bronze import BronzeAptTransaction, BronzeInterestRate, BronzeMigration
from younggeul_core.state.gold import GoldDistrictMonthlyMetrics
from younggeul_core.state.simulation import ScenarioSpec, SnapshotRef
from younggeul_core.storage.snapshot import SnapshotManifest

from .forecaster import forecast_baseline, generate_baseline_report
from .pipeline import BronzeInput, run_pipeline
from .runtime_version import get_runtime_version
from .simulation.event_store import InMemoryEventStore
from .simulation.evidence.store import InMemoryEvidenceStore
from .simulation.graph import build_simulation_graph
from .simulation.graph_state import seed_graph_state
from .simulation.adapters.filesystem_snapshot_reader import FilesystemSnapshotReader
from .simulation.metrics import init_metrics, shutdown_metrics
from .simulation.schemas.report import RenderedReport
from .simulation.tracing import init_tracing, shutdown_tracing
from .snapshot import publish_snapshot, resolve_snapshot
from .web.config import validate_max_rounds, validate_model_id


def _output(ctx: click.Context, data: dict[str, Any], text_lines: list[str]) -> None:
    if ctx.obj and ctx.obj.get("output") == "json":
        click.echo(json.dumps(data, ensure_ascii=False, default=str))
        return

    for line in text_lines:
        click.echo(line)


def _shutdown_observability() -> None:
    try:
        shutdown_tracing()
    except Exception:
        pass
    try:
        shutdown_metrics()
    except Exception:
        pass


def _emit_version(ctx: click.Context, _: click.Option, value: bool) -> None:
    if not value or ctx.resilient_parsing:
        return
    click.echo(get_runtime_version())
    ctx.exit()


def _fixture_bronze_input() -> BronzeInput:
    now = datetime.now(timezone.utc)
    return BronzeInput(
        apt_transactions=[
            BronzeAptTransaction(
                ingest_timestamp=now,
                source_id="molit.apartment.transactions",
                raw_response_hash="a" * 64,
                deal_amount="82,000",
                build_year="2016",
                deal_year="2025",
                deal_month="7",
                deal_day="15",
                dong="역삼동",
                apt_name="래미안",
                floor="12",
                area_exclusive="84.99",
                jibun="123-45",
                road_name="테헤란로",
                serial_number="2025-001",
                sgg_code="11680",
                umd_code="10300",
            ),
            BronzeAptTransaction(
                ingest_timestamp=now,
                source_id="molit.apartment.transactions",
                raw_response_hash="a" * 64,
                deal_amount="82,000",
                build_year="2016",
                deal_year="2025",
                deal_month="7",
                deal_day="15",
                dong="역삼동",
                apt_name="래미안",
                floor="12",
                area_exclusive="84.99",
                jibun="123-45",
                road_name="테헤란로",
                serial_number="2025-001",
                sgg_code="11680",
                umd_code="10300",
            ),
            BronzeAptTransaction(
                ingest_timestamp=now,
                source_id="molit.apartment.transactions",
                raw_response_hash="d" * 64,
                deal_amount="84,000",
                build_year="2018",
                deal_year="2025",
                deal_month="7",
                deal_day="20",
                dong="역삼동",
                apt_name="아이파크",
                floor="9",
                area_exclusive="84.99",
                jibun="223-45",
                road_name="테헤란로",
                serial_number="2025-002",
                sgg_code="11680",
                umd_code="10300",
            ),
        ],
        interest_rates=[
            BronzeInterestRate(
                ingest_timestamp=now,
                source_id="bank_of_korea_base_rate",
                raw_response_hash="b" * 64,
                date="2025-07-01",
                rate_type="base_rate",
                rate_value="3.50",
                unit="%",
            )
        ],
        migrations=[
            BronzeMigration(
                ingest_timestamp=now,
                source_id="kostat_population_migration",
                raw_response_hash="c" * 64,
                year="2025",
                month="07",
                region_code="11",
                region_name="서울특별시",
                in_count="150000",
                out_count="140000",
                net_count="10000",
            )
        ],
    )


def _load_gold_rows(data_dir: Path) -> list[GoldDistrictMonthlyMetrics]:
    primary = data_dir / "gold_district_monthly_metrics.jsonl"
    candidate_files = [primary] if primary.exists() else sorted(data_dir.glob("*.jsonl"))
    if not candidate_files:
        raise click.ClickException(f"No gold JSONL files found in {data_dir}")

    rows: list[GoldDistrictMonthlyMetrics] = []
    target_file = candidate_files[0]
    for line in target_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(GoldDistrictMonthlyMetrics.model_validate_json(line))
        except ValidationError as exc:
            raise click.ClickException(f"Invalid gold JSONL content in {target_file}") from exc
    return rows


def _snapshot_ref_from_manifest(manifest: Any) -> SnapshotRef:
    return SnapshotRef(
        dataset_snapshot_id=manifest.dataset_snapshot_id,
        created_at=manifest.created_at,
        table_count=len(manifest.table_entries),
    )


_SNAPSHOT_DIR_NAME_RE = re.compile(r"^[0-9a-f]{64}$")


def _add_months(year: int, month: int, months: int) -> date:
    total_month = (year * 12) + (month - 1) + months
    return date(total_month // 12, (total_month % 12) + 1, 1)


def _parse_period_start(period: str) -> date:
    year_str, month_str = period.split("-", maxsplit=1)
    return date(int(year_str), int(month_str), 1)


def _parse_gus_csv(gus: str) -> list[str]:
    target_gus = [gu.strip() for gu in gus.split(",") if gu.strip()]
    if not target_gus:
        raise click.ClickException("--gus must include at least one gu code")
    return target_gus


def _resolve_single_snapshot_manifest(snapshot_dir: Path) -> SnapshotManifest:
    snapshot_candidates = [
        candidate
        for candidate in sorted(snapshot_dir.iterdir(), key=lambda item: item.name)
        if candidate.is_dir() and _SNAPSHOT_DIR_NAME_RE.fullmatch(candidate.name)
    ]
    if not snapshot_candidates:
        raise click.ClickException(f"No snapshot subdirectories found in {snapshot_dir}")
    if len(snapshot_candidates) > 1:
        raise click.ClickException(
            f"Multiple snapshots found in {snapshot_dir}; please leave only one snapshot directory for simulate"
        )

    manifest_path = snapshot_candidates[0] / "manifest.json"
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise click.ClickException(f"Snapshot manifest not found: {manifest_path}") from exc
    except (json.JSONDecodeError, OSError) as exc:
        raise click.ClickException(f"Invalid manifest JSON at {manifest_path}") from exc

    try:
        return SnapshotManifest.model_validate(payload)
    except ValidationError as exc:
        raise click.ClickException(f"Invalid manifest schema at {manifest_path}") from exc


def _build_cli_live_roster() -> dict[str, Any]:
    return {
        "seed": "cli-live",
        "buckets": [
            {
                "role": "buyer",
                "count": 1,
                "capital_min_multiplier": 1.0,
                "capital_max_multiplier": 1.2,
                "holdings_min": 0,
                "holdings_max": 0,
                "risk_min": 0.5,
                "risk_max": 0.5,
                "sentiment_bias": "neutral",
            },
            {
                "role": "investor",
                "count": 1,
                "capital_min_multiplier": 0.0,
                "capital_max_multiplier": 0.0,
                "holdings_min": 1,
                "holdings_max": 1,
                "risk_min": 0.5,
                "risk_max": 0.5,
                "sentiment_bias": "neutral",
            },
        ],
    }


def _extract_rendered_report(
    final_state: dict[str, Any], event_store: InMemoryEventStore, run_id: str
) -> RenderedReport:
    rendered = final_state.get("rendered_report")
    if isinstance(rendered, RenderedReport):
        return rendered
    if isinstance(rendered, dict):
        try:
            return RenderedReport.model_validate(rendered)
        except ValidationError as exc:
            raise click.ClickException("Invalid rendered_report in final state") from exc

    events = event_store.get_events_by_type(run_id, "REPORT_RENDERED")
    if not events:
        raise click.ClickException("Simulation did not produce a rendered report")
    payload = events[-1].payload
    if "rendered_report" not in payload:
        raise click.ClickException("REPORT_RENDERED event missing rendered_report payload")

    try:
        return RenderedReport.model_validate(payload["rendered_report"])
    except ValidationError as exc:
        raise click.ClickException("Invalid rendered_report payload") from exc


@click.group(name="younggeul")
@click.option("--output", type=click.Choice(["text", "json"]), default="text", show_default=True)
@click.option("--version", is_flag=True, is_eager=True, callback=_emit_version, expose_value=False)
@click.pass_context
def main(ctx: click.Context, output: str) -> None:
    """Run the top-level Younggeul CLI group."""
    ctx.ensure_object(dict)
    ctx.obj["output"] = output
    init_tracing()
    init_metrics()
    ctx.call_on_close(_shutdown_observability)


@main.command("ingest")
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=Path("./output/pipeline"),
    show_default=True,
)
@click.option(
    "--source",
    type=click.Choice(["fixture", "live"]),
    default="fixture",
    show_default=True,
    help="Data source: 'fixture' uses bundled toy data; 'live' fetches from real APIs via kpubdata.",
)
@click.option(
    "--gu",
    "lawd_code",
    default=None,
    help="5-digit MOLIT sigungu code (live mode, e.g. 11680). Mutually exclusive with --gus.",
)
@click.option(
    "--gus",
    "lawd_codes_csv",
    default=None,
    help="Comma-separated 5-digit MOLIT sigungu codes (live mode, e.g. 11680,11440). Mutually exclusive with --gu.",
)
@click.option(
    "--month",
    "deal_ym",
    default=None,
    help="Single target month in YYYYMM format (live mode, e.g. 202503). Mutually exclusive with --months.",
)
@click.option(
    "--months",
    "deal_yms_csv",
    default=None,
    help="Comma-separated list of YYYYMM months (live mode, e.g. 202403,202503). Enables YoY/MoM in Gold output. Mutually exclusive with --month.",
)
@click.pass_context
def ingest_command(
    ctx: click.Context,
    output_dir: Path,
    source: str,
    lawd_code: str | None,
    lawd_codes_csv: str | None,
    deal_ym: str | None,
    deal_yms_csv: str | None,
) -> None:
    """Ingest Bronze data and write Gold JSONL output.

    Default ``--source=fixture`` uses bundled toy data and requires no API keys.
    ``--source=live`` requires exactly one of ``--gu`` or ``--gus`` and exactly
    one of ``--month`` or ``--months`` plus the ``KPUBDATA_DATAGO_API_KEY`` and
    ``KPUBDATA_BOK_API_KEY`` environment variables.
    """
    try:
        if source == "live":
            if lawd_code and lawd_codes_csv:
                raise click.ClickException("--gu and --gus are mutually exclusive")
            if not lawd_code and not lawd_codes_csv:
                raise click.ClickException("exactly one of --gu or --gus is required when --source=live")
            if deal_ym and deal_yms_csv:
                raise click.ClickException("--month and --months are mutually exclusive")
            if not deal_ym and not deal_yms_csv:
                raise click.ClickException("exactly one of --month or --months is required when --source=live")
            from younggeul_app_kr_seoul_apartment.connectors.client_factory import build_client
            from younggeul_app_kr_seoul_apartment.pipeline_live import run_live_ingest_gus_months

            if lawd_codes_csv:
                lawd_codes = [code.strip() for code in lawd_codes_csv.split(",") if code.strip()]
            else:
                assert lawd_code is not None
                lawd_codes = [lawd_code]

            if deal_yms_csv:
                deal_yms = [ym.strip() for ym in deal_yms_csv.split(",") if ym.strip()]
            else:
                assert deal_ym is not None
                deal_yms = [deal_ym]

            client = build_client()
            bronze = run_live_ingest_gus_months(client=client, lawd_codes=lawd_codes, deal_yms=deal_yms)
        else:
            bronze = _fixture_bronze_input()
        result = run_pipeline(bronze)

        output_dir.mkdir(parents=True, exist_ok=True)
        gold_path = output_dir / "gold_district_monthly_metrics.jsonl"
        payload = "\n".join(row.model_dump_json() for row in result.gold)
        if payload:
            payload = f"{payload}\n"
        gold_path.write_text(payload, encoding="utf-8")

        data = {
            "status": "success",
            "source": source,
            "silver_apt_count": len(result.silver.apt_transactions),
            "silver_rate_count": len(result.silver.interest_rates),
            "silver_migration_count": len(result.silver.migrations),
            "gold_count": len(result.gold),
        }
        text_lines = [
            "Ingest completed successfully.",
            f"Silver apartment records: {data['silver_apt_count']}",
            f"Silver interest rate records: {data['silver_rate_count']}",
            f"Silver migration records: {data['silver_migration_count']}",
            f"Gold records: {data['gold_count']}",
            f"Wrote gold JSONL: {gold_path}",
        ]
        _output(ctx, data, text_lines)
    except click.ClickException:
        raise
    except click.exceptions.Exit:
        raise
    except SystemExit:
        raise
    except Exception as exc:
        click.echo(f"Fatal error: {exc}", err=True)
        sys.exit(1)


@main.group("snapshot")
def snapshot_group() -> None:
    """Manage dataset snapshots used by downstream commands."""
    pass


@snapshot_group.command("publish")
@click.option(
    "--data-dir",
    type=click.Path(path_type=Path, exists=True, file_okay=False, dir_okay=True),
    required=True,
)
@click.option(
    "--snapshot-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=Path("./output/snapshots"),
    show_default=True,
)
@click.pass_context
def snapshot_publish_command(ctx: click.Context, data_dir: Path, snapshot_dir: Path) -> None:
    """Publish a snapshot from Gold JSONL files in a data directory."""
    try:
        gold_rows = _load_gold_rows(data_dir)
        snapshot_ref = publish_snapshot(gold_rows, snapshot_dir)
        data = {
            "dataset_snapshot_id": snapshot_ref.dataset_snapshot_id,
            "created_at": snapshot_ref.created_at.isoformat(),
            "table_count": snapshot_ref.table_count,
        }
        text_lines = [
            "Snapshot published successfully.",
            f"dataset_snapshot_id: {snapshot_ref.dataset_snapshot_id}",
            f"created_at: {snapshot_ref.created_at.isoformat()}",
            f"table_count: {snapshot_ref.table_count}",
        ]
        _output(ctx, data, text_lines)
    except click.ClickException:
        raise
    except SystemExit:
        raise
    except Exception as exc:
        click.echo(f"Fatal error: {exc}", err=True)
        sys.exit(1)


@snapshot_group.command("list")
@click.option(
    "--snapshot-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=Path("./output/snapshots"),
    show_default=True,
)
@click.pass_context
def snapshot_list_command(ctx: click.Context, snapshot_dir: Path) -> None:
    """List available dataset snapshots from the snapshot directory."""
    try:
        items: list[dict[str, Any]] = []
        if snapshot_dir.exists():
            for candidate in sorted(snapshot_dir.iterdir(), key=lambda item: item.name):
                if not candidate.is_dir():
                    continue
                manifest_path = candidate / "manifest.json"
                if not manifest_path.exists():
                    continue
                try:
                    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
                    created_at = manifest_payload["created_at"]
                    table_entries = manifest_payload["table_entries"]
                except (KeyError, json.JSONDecodeError, TypeError) as exc:
                    raise click.ClickException(f"Invalid manifest schema at {manifest_path}") from exc
                items.append(
                    {
                        "snapshot_id": str(manifest_payload["dataset_snapshot_id"]),
                        "created_at": str(created_at),
                        "table_count": len(table_entries),
                        "total_records": sum(int(entry.get("record_count", 0)) for entry in table_entries),
                    }
                )

        data = {"count": len(items), "snapshots": items}
        if items:
            text_lines = [
                f"Found {len(items)} snapshot(s) in {snapshot_dir}.",
                *[
                    (
                        f"- {item['snapshot_id']} "
                        f"(created_at={item['created_at']}, tables={item['table_count']}, "
                        f"records={item['total_records']})"
                    )
                    for item in items
                ],
            ]
        else:
            text_lines = [f"No snapshots found in {snapshot_dir}."]
        _output(ctx, data, text_lines)
    except click.ClickException:
        raise
    except click.exceptions.Exit:
        raise
    except SystemExit:
        raise
    except Exception as exc:
        click.echo(f"Fatal error: {exc}", err=True)
        sys.exit(1)


@main.command("baseline")
@click.option("--snapshot-id", type=str, default="latest", show_default=True)
@click.option(
    "--snapshot-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=Path("./output/snapshots"),
    show_default=True,
)
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=Path("./output/baseline"),
    show_default=True,
)
@click.pass_context
def baseline_command(ctx: click.Context, snapshot_id: str, snapshot_dir: Path, output_dir: Path) -> None:
    """Generate baseline forecasts from a stored snapshot."""
    try:
        manifest, metrics = resolve_snapshot(snapshot_id, snapshot_dir)
        snapshot_ref = _snapshot_ref_from_manifest(manifest)
        forecasts = forecast_baseline(metrics)
        report_path = generate_baseline_report(snapshot_ref, forecasts, output_dir)

        data = {
            "snapshot_id": snapshot_ref.dataset_snapshot_id,
            "forecast_count": len(forecasts),
            "report_file": str(report_path),
            "forecasts": [forecast.model_dump(mode="json") for forecast in forecasts],
        }
        text_lines = [
            "Baseline forecast completed.",
            f"Snapshot: {snapshot_ref.dataset_snapshot_id}",
            f"Forecasts: {len(forecasts)}",
            f"Report: {report_path}",
        ]
        _output(ctx, data, text_lines)
    except (FileNotFoundError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    except click.ClickException:
        raise
    except Exception as exc:
        click.echo(f"Fatal error: {exc}", err=True)
        sys.exit(1)


@main.command("simulate")
@click.option("--query", required=True, type=str)
@click.option("--max-rounds", type=int, default=3, show_default=True)
@click.option("--model-id", type=str, default="stub", show_default=True)
@click.option("--run-name", type=str, default="cli-run", show_default=True)
@click.option(
    "--snapshot-dir",
    type=click.Path(path_type=Path, exists=True, file_okay=False, dir_okay=True),
    default=None,
)
@click.option(
    "--baseline-dir",
    type=click.Path(path_type=Path, exists=True, file_okay=False, dir_okay=True),
    default=None,
)
@click.option("--gus", type=str, default=None)
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=Path("./output/simulation"),
    show_default=True,
)
@click.option(
    "--render",
    "render_backend",
    type=click.Choice(["legacy", "abdp"]),
    default="legacy",
    show_default=True,
    help="Rendering backend for the simulation report. 'legacy' writes the existing markdown only; "
    "'abdp' additionally writes a deterministic JSON report via abdp.reporting.render_json_report "
    "(requires the [abdp] extra). See ADR-012.",
)
@click.pass_context
def simulate_command(
    ctx: click.Context,
    query: str,
    max_rounds: int,
    model_id: str,
    run_name: str,
    snapshot_dir: Path | None,
    baseline_dir: Path | None,
    gus: str | None,
    output_dir: Path,
    render_backend: str,
) -> None:
    """Run the simulation graph and save a rendered Markdown report."""
    try:
        validate_max_rounds(max_rounds)
        validate_model_id(model_id)
        if gus is not None and snapshot_dir is None:
            raise click.ClickException("--gus requires --snapshot-dir")
        if baseline_dir is not None and snapshot_dir is None:
            raise click.ClickException("--baseline-dir requires --snapshot-dir")

        event_store = InMemoryEventStore()
        evidence_store = InMemoryEvidenceStore()

        run_id = str(uuid4())
        if snapshot_dir is None:
            graph = build_simulation_graph(event_store, evidence_store=evidence_store)
            initial_state = seed_graph_state(query, run_id=run_id, run_name=run_name, model_id=model_id)
        else:
            manifest = _resolve_single_snapshot_manifest(snapshot_dir)
            snapshot_ref = _snapshot_ref_from_manifest(manifest)
            snapshot_reader = FilesystemSnapshotReader(snapshot_dir, baseline_dir)
            coverage = snapshot_reader.get_coverage(snapshot_ref)

            target_gus = _parse_gus_csv(gus) if gus is not None else coverage.available_gu_codes
            latest_period = _parse_period_start(coverage.max_period)
            target_period_start = _add_months(latest_period.year, latest_period.month, 1)
            target_period_end = _add_months(latest_period.year, latest_period.month, max(1, max_rounds))
            scenario = ScenarioSpec(
                scenario_name="cli-live",
                target_gus=target_gus,
                target_period_start=target_period_start,
                target_period_end=target_period_end,
                shocks=[],
            )
            participant_roster = _build_cli_live_roster()
            graph = build_simulation_graph(
                event_store,
                evidence_store=evidence_store,
                snapshot_reader=snapshot_reader,
            )
            initial_state = seed_graph_state(
                query,
                run_id=run_id,
                run_name=run_name,
                model_id=model_id,
                snapshot=snapshot_ref,
                scenario=scenario,
                participant_roster=participant_roster,
            )

        initial_state["max_rounds"] = max_rounds
        final_state = graph.invoke(initial_state)

        rendered_report = _extract_rendered_report(final_state, event_store, run_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        report_file = output_dir / f"simulation_report_{run_id}.md"
        report_file.write_text(rendered_report.markdown, encoding="utf-8")

        report_json_file: Path | None = None
        if render_backend == "abdp":
            from younggeul_core._compat.reporting import render_json_report

            report_json_file = output_dir / f"simulation_report_{run_id}.json"
            report_json_file.write_text(
                render_json_report(rendered_report.model_dump(mode="json")),
                encoding="utf-8",
            )

        data = {
            "run_id": run_id,
            "round_no": int(final_state.get("round_no", 0)),
            "event_ref_count": len(final_state.get("event_refs", [])),
            "warnings": list(final_state.get("warnings", [])),
            "report_file": str(report_file),
            "report_json_file": str(report_json_file) if report_json_file else None,
            "rendered_report": rendered_report.model_dump(mode="json"),
        }
        text_lines = [rendered_report.markdown, "", f"Saved report: {report_file}"]
        if report_json_file is not None:
            text_lines.append(f"Saved JSON report: {report_json_file}")
        _output(ctx, data, text_lines)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    except click.ClickException:
        raise
    except Exception as exc:
        click.echo(f"Fatal error: {exc}", err=True)
        sys.exit(1)


@main.command("report")
@click.option("--report-file", type=click.Path(path_type=Path, dir_okay=False), required=True)
@click.pass_context
def report_command(ctx: click.Context, report_file: Path) -> None:
    """Print an existing report file to the selected output format."""
    try:
        if not report_file.exists() or not report_file.is_file():
            raise click.ClickException(f"Report file not found: {report_file}")
        content = report_file.read_text(encoding="utf-8")
        _output(ctx, {"file": str(report_file), "content": content}, [content])
    except click.ClickException:
        raise
    except Exception as exc:
        click.echo(f"Fatal error: {exc}", err=True)
        sys.exit(1)


@main.command("eval")
@click.option("--output-dir", type=str, default="eval_results", show_default=True)
@click.pass_context
def eval_command(ctx: click.Context, output_dir: str) -> None:
    """Execute eval-marked tests and persist evaluation summaries."""
    try:
        base_dir = Path(output_dir)
        base_dir.mkdir(parents=True, exist_ok=True)

        junit_path = base_dir / "eval_junit.xml"
        json_path = base_dir / "eval_summary.json"

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-m",
                "eval",
                f"--junitxml={junit_path}",
                "-v",
                "--tb=short",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.stdout:
            click.echo(result.stdout)
        if result.stderr:
            click.echo(result.stderr, err=True)

        summary = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "exit_code": result.returncode,
            "status": "passed" if result.returncode == 0 else "failed",
            "junit_xml": str(junit_path),
        }
        json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

        _output(
            ctx,
            {"status": "success", "summary": summary, "summary_file": str(json_path)},
            [f"Eval summary written to {json_path}", f"Exit code: {result.returncode}"],
        )
        ctx.exit(result.returncode)
    except click.ClickException:
        raise
    except click.exceptions.Exit:
        raise
    except SystemExit:
        raise
    except Exception as exc:
        click.echo(f"Fatal error: {exc}", err=True)
        sys.exit(1)


@main.command("serve", help="Start the web UI server.")
@click.option("--host", default="0.0.0.0", show_default=True)
@click.option("--port", default=8000, type=int, show_default=True)
def serve_command(host: str, port: int) -> None:
    import uvicorn

    from .web.app import create_app

    app = create_app()
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
