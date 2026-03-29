from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from younggeul_app_kr_seoul_apartment.forecaster import forecast_baseline, generate_baseline_report
from younggeul_app_kr_seoul_apartment.pipeline import BronzeInput, run_pipeline
from younggeul_app_kr_seoul_apartment.snapshot import publish_snapshot, resolve_snapshot
from younggeul_core.state.bronze import BronzeAptTransaction, BronzeInterestRate, BronzeMigration

_FIXED_NOW = datetime(2026, 3, 29, 12, 0, 0, tzinfo=timezone.utc)


def _make_bronze_apt(**overrides: Any) -> BronzeAptTransaction:
    payload: dict[str, Any] = {
        "ingest_timestamp": _FIXED_NOW,
        "source_id": "molit.apartment.transactions",
        "raw_response_hash": "a" * 64,
        "deal_amount": "82,000",
        "build_year": "2016",
        "deal_year": "2025",
        "deal_month": "1",
        "deal_day": "15",
        "dong": "역삼동",
        "apt_name": "래미안",
        "floor": "12",
        "area_exclusive": "84.99",
        "jibun": "123-45",
        "road_name": "테헤란로",
        "serial_number": "2025-001",
        "sgg_code": "11680",
        "umd_code": "10300",
    }
    payload.update(overrides)
    return BronzeAptTransaction(**payload)


def _make_bronze_rate(**overrides: Any) -> BronzeInterestRate:
    payload: dict[str, Any] = {
        "ingest_timestamp": _FIXED_NOW,
        "source_id": "bank_of_korea_base_rate",
        "raw_response_hash": "b" * 64,
        "date": "2025-01-01",
        "rate_type": "base_rate",
        "rate_value": "3.50",
        "unit": "%",
    }
    payload.update(overrides)
    return BronzeInterestRate(**payload)


def _make_bronze_migration(**overrides: Any) -> BronzeMigration:
    payload: dict[str, Any] = {
        "ingest_timestamp": _FIXED_NOW,
        "source_id": "kostat_population_migration",
        "raw_response_hash": "c" * 64,
        "year": "2025",
        "month": "01",
        "region_code": "11",
        "region_name": "서울특별시",
        "in_count": "150000",
        "out_count": "140000",
        "net_count": "10000",
    }
    payload.update(overrides)
    return BronzeMigration(**payload)


def _hex64(index: int) -> str:
    return f"{index:064x}"


def _make_chain_bronze_input() -> BronzeInput:
    apt_transactions: list[BronzeAptTransaction] = []
    hash_index = 1

    monthly_prices = [
        ("2025", "1", ["81,000", "83,000"], ["70,000", "72,000"]),
        ("2025", "2", ["85,000", "87,000", "89,000"], ["71,000", "73,000", "74,000"]),
        ("2025", "3", ["90,000", "92,000", "94,000", "96,000"], ["72,000", "75,000", "77,000", "79,000"]),
    ]

    for year, month, gangnam_prices, seocho_prices in monthly_prices:
        month_num = int(month)

        for seq, deal_amount in enumerate(gangnam_prices, start=1):
            apt_transactions.append(
                _make_bronze_apt(
                    serial_number=f"{year}{month_num:02d}-11680-{seq:03d}",
                    raw_response_hash=_hex64(hash_index),
                    deal_amount=deal_amount,
                    deal_year=year,
                    deal_month=str(month_num),
                    deal_day=f"{seq:02d}",
                    sgg_code="11680",
                    dong="역삼동",
                    umd_code="10300",
                    apt_name=f"강남트렌드-{year}-{month_num:02d}-{seq}",
                )
            )
            hash_index += 1

        for seq, deal_amount in enumerate(seocho_prices, start=1):
            apt_transactions.append(
                _make_bronze_apt(
                    serial_number=f"{year}{month_num:02d}-11650-{seq:03d}",
                    raw_response_hash=_hex64(hash_index),
                    deal_amount=deal_amount,
                    deal_year=year,
                    deal_month=str(month_num),
                    deal_day=f"{seq + 10:02d}",
                    sgg_code="11650",
                    dong="서초동",
                    umd_code="10100",
                    apt_name=f"서초트렌드-{year}-{month_num:02d}-{seq}",
                )
            )
            hash_index += 1

    interest_rates = [
        _make_bronze_rate(date="2025-01-01", rate_value="3.50", raw_response_hash=_hex64(10_001)),
        _make_bronze_rate(date="2025-02-01", rate_value="3.25", raw_response_hash=_hex64(10_002)),
        _make_bronze_rate(date="2025-03-01", rate_value="3.00", raw_response_hash=_hex64(10_003)),
    ]

    migrations = [
        _make_bronze_migration(year="2025", month="01", net_count="10000", raw_response_hash=_hex64(20_001)),
        _make_bronze_migration(year="2025", month="02", net_count="12000", raw_response_hash=_hex64(20_002)),
        _make_bronze_migration(year="2025", month="03", net_count="14000", raw_response_hash=_hex64(20_003)),
    ]

    return BronzeInput(
        apt_transactions=apt_transactions,
        interest_rates=interest_rates,
        migrations=migrations,
    )


def _run_chain(
    bronze: BronzeInput,
    snapshots_dir: Path,
    reports_dir: Path,
) -> tuple[Any, Any, Any, list[Any], list[Any], Path]:
    result = run_pipeline(bronze)
    snapshot_ref = publish_snapshot(result.gold, snapshots_dir)
    manifest, gold_rows = resolve_snapshot(snapshot_ref.dataset_snapshot_id, snapshots_dir)
    forecasts = forecast_baseline(gold_rows)
    report_path = generate_baseline_report(snapshot_ref, forecasts, reports_dir)
    return result, snapshot_ref, manifest, gold_rows, forecasts, report_path


def _read_report(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalized_report(path: Path) -> str:
    payload = _read_report(path)
    payload.pop("generated_at", None)
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


class TestChainEndToEnd:
    def test_full_chain_produces_report_artifact(self, tmp_path: Path) -> None:
        bronze = _make_chain_bronze_input()

        _, snapshot_ref, _, _, forecasts, report_path = _run_chain(
            bronze,
            tmp_path / "snapshots",
            tmp_path / "reports",
        )

        assert report_path.exists()
        assert report_path.is_file()
        assert report_path.suffix == ".json"

        payload = _read_report(report_path)
        assert payload["report_type"] == "baseline_forecast"
        assert payload["snapshot"]["dataset_snapshot_id"] == snapshot_ref.dataset_snapshot_id
        assert payload["summary"]["total_districts"] == len(forecasts)

    def test_pipeline_produces_enriched_gold_with_mom_and_yoy(self) -> None:
        bronze = _make_chain_bronze_input()

        result = run_pipeline(bronze)

        assert len(result.gold) == 6

        gold_by_key = {(row.gu_code, row.period): row for row in result.gold}
        for gu_code in {"11680", "11650"}:
            assert gold_by_key[(gu_code, "2025-01")].mom_price_change is None
            assert gold_by_key[(gu_code, "2025-01")].mom_volume_change is None
            assert gold_by_key[(gu_code, "2025-02")].mom_price_change is not None
            assert gold_by_key[(gu_code, "2025-02")].mom_volume_change is not None
            assert gold_by_key[(gu_code, "2025-03")].mom_price_change is not None
            assert gold_by_key[(gu_code, "2025-03")].mom_volume_change is not None

        assert all(row.yoy_price_change is None for row in result.gold)
        assert all(row.yoy_volume_change is None for row in result.gold)
        assert all(isinstance(row.base_interest_rate, Decimal) for row in result.gold)

    def test_snapshot_round_trips_with_integrity(self, tmp_path: Path) -> None:
        bronze = _make_chain_bronze_input()

        result = run_pipeline(bronze)
        snapshot_ref = publish_snapshot(result.gold, tmp_path / "snapshots")
        manifest, gold_rows = resolve_snapshot(snapshot_ref.dataset_snapshot_id, tmp_path / "snapshots")

        assert manifest.dataset_snapshot_id == snapshot_ref.dataset_snapshot_id
        assert manifest.total_records == len(result.gold)
        assert len(gold_rows) == len(result.gold)

        expected = [
            row.model_dump_json()
            for row in sorted(
                result.gold,
                key=lambda row: (row.gu_code, row.period),
            )
        ]
        actual = [row.model_dump_json() for row in gold_rows]
        assert actual == expected

    def test_resolve_snapshot_by_latest(self, tmp_path: Path) -> None:
        bronze = _make_chain_bronze_input()

        result = run_pipeline(bronze)
        snapshot_ref = publish_snapshot(result.gold, tmp_path / "snapshots")
        manifest, gold_rows = resolve_snapshot("latest", tmp_path / "snapshots")

        assert manifest.dataset_snapshot_id == snapshot_ref.dataset_snapshot_id
        assert len(gold_rows) == len(result.gold)

    def test_forecasts_cover_all_districts(self, tmp_path: Path) -> None:
        bronze = _make_chain_bronze_input()

        _, _, _, gold_rows, forecasts, _ = _run_chain(
            bronze,
            tmp_path / "snapshots",
            tmp_path / "reports",
        )

        gold_gu_codes = {row.gu_code for row in gold_rows}
        forecast_gu_codes = {forecast.gu_code for forecast in forecasts}

        assert forecast_gu_codes == gold_gu_codes
        assert len(forecasts) == 2

    def test_forecasts_are_deterministic(self, tmp_path: Path) -> None:
        bronze = _make_chain_bronze_input()

        _, snapshot_ref_a, _, _, forecasts_a, _ = _run_chain(
            bronze,
            tmp_path / "run-a" / "snapshots",
            tmp_path / "run-a" / "reports",
        )
        _, snapshot_ref_b, _, _, forecasts_b, _ = _run_chain(
            bronze,
            tmp_path / "run-b" / "snapshots",
            tmp_path / "run-b" / "reports",
        )

        assert snapshot_ref_a.dataset_snapshot_id == snapshot_ref_b.dataset_snapshot_id
        assert forecasts_a == forecasts_b

    def test_report_contains_correct_summary_counts(self, tmp_path: Path) -> None:
        bronze = _make_chain_bronze_input()

        _, _, _, _, forecasts, report_path = _run_chain(
            bronze,
            tmp_path / "snapshots",
            tmp_path / "reports",
        )

        payload = _read_report(report_path)
        summary = payload["summary"]
        direction_counts = summary["direction_counts"]

        assert summary["total_districts"] == len(forecasts)
        assert sum(direction_counts.values()) == summary["total_districts"]

    def test_report_includes_snapshot_metadata(self, tmp_path: Path) -> None:
        bronze = _make_chain_bronze_input()

        _, snapshot_ref, _, _, _, report_path = _run_chain(
            bronze,
            tmp_path / "snapshots",
            tmp_path / "reports",
        )

        payload = _read_report(report_path)
        snapshot_payload = payload["snapshot"]

        assert snapshot_payload["dataset_snapshot_id"] == snapshot_ref.dataset_snapshot_id
        assert snapshot_payload["created_at"] == snapshot_ref.created_at.isoformat()
        assert snapshot_payload["table_count"] == snapshot_ref.table_count


class TestChainDeterminism:
    def test_full_chain_is_byte_deterministic(self, tmp_path: Path) -> None:
        bronze = _make_chain_bronze_input()

        _, snapshot_ref_a, _, _, forecasts_a, report_path_a = _run_chain(
            bronze,
            tmp_path / "run-a" / "snapshots",
            tmp_path / "run-a" / "reports",
        )
        _, snapshot_ref_b, _, _, forecasts_b, _ = _run_chain(
            bronze,
            tmp_path / "run-b" / "snapshots",
            tmp_path / "run-b" / "reports",
        )

        replay_report_path = generate_baseline_report(
            snapshot_ref_a,
            forecasts_a,
            tmp_path / "replay" / "reports",
        )

        assert snapshot_ref_a.dataset_snapshot_id == snapshot_ref_b.dataset_snapshot_id
        assert forecasts_a == forecasts_b
        assert _normalized_report(report_path_a) == _normalized_report(replay_report_path)
