from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest

from younggeul_app_kr_seoul_apartment.snapshot import publish_snapshot, resolve_snapshot
from younggeul_core.state.gold import GoldDistrictMonthlyMetrics
from younggeul_core.state.simulation import SnapshotRef
from younggeul_core.storage.snapshot import SnapshotManifest, SnapshotTableEntry


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
        "dataset_snapshot_id": "free-form-gold-snapshot-id",
    }
    payload.update(overrides)
    return GoldDistrictMonthlyMetrics(**payload)


def _snapshot_dir(base_dir: Path, snapshot_id: str) -> Path:
    return base_dir / snapshot_id


def _manifest_path(base_dir: Path, snapshot_id: str) -> Path:
    return _snapshot_dir(base_dir, snapshot_id) / "manifest.json"


def _table_path(base_dir: Path, snapshot_id: str) -> Path:
    return _snapshot_dir(base_dir, snapshot_id) / "gold_district_monthly_metrics.jsonl"


def _load_manifest(base_dir: Path, snapshot_id: str) -> dict[str, Any]:
    payload = json.loads(_manifest_path(base_dir, snapshot_id).read_text(encoding="utf-8"))
    return cast(dict[str, Any], payload)


def _make_jsonl_bytes(rows: list[GoldDistrictMonthlyMetrics]) -> bytes:
    if not rows:
        return b""
    return b"\n".join(row.model_dump_json().encode("utf-8") for row in rows) + b"\n"


def _write_manual_snapshot(
    base_dir: Path,
    content: bytes,
    created_at: datetime,
) -> str:

    table_hash = hashlib.sha256(content).hexdigest()
    dataset_snapshot_id = SnapshotManifest.compute_snapshot_id({"gold_district_monthly_metrics": table_hash})

    snapshot_dir = base_dir / dataset_snapshot_id
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    table_file = snapshot_dir / "gold_district_monthly_metrics.jsonl"
    table_file.write_bytes(content)

    manifest = SnapshotManifest(
        dataset_snapshot_id=dataset_snapshot_id,
        created_at=created_at,
        table_entries=[
            SnapshotTableEntry(
                table_name="gold_district_monthly_metrics",
                table_hash=table_hash,
                record_count=len(content.splitlines()),
                schema_version="1.0.0",
                file_format="jsonl",
            )
        ],
    )
    (snapshot_dir / "manifest.json").write_text(manifest.model_dump_json(), encoding="utf-8")
    return dataset_snapshot_id


class TestPublishSnapshot:
    def test_returns_snapshot_ref_with_expected_fields(self, tmp_path: Path) -> None:
        row = _make_gold()

        ref = publish_snapshot([row], tmp_path)

        assert isinstance(ref, SnapshotRef)
        assert len(ref.dataset_snapshot_id) == 64
        assert ref.table_count == 1
        assert ref.created_at.tzinfo is not None

    def test_creates_snapshot_directory_and_expected_files(self, tmp_path: Path) -> None:
        ref = publish_snapshot([_make_gold()], tmp_path)

        snapshot_dir = _snapshot_dir(tmp_path, ref.dataset_snapshot_id)
        assert snapshot_dir.is_dir()
        assert _manifest_path(tmp_path, ref.dataset_snapshot_id).is_file()
        assert _table_path(tmp_path, ref.dataset_snapshot_id).is_file()

    def test_writes_rows_sorted_by_gu_code_and_period(self, tmp_path: Path) -> None:
        rows = [
            _make_gold(gu_code="11710", gu_name="송파구", period="2025-08"),
            _make_gold(gu_code="11680", gu_name="강남구", period="2025-08"),
            _make_gold(gu_code="11680", gu_name="강남구", period="2025-07"),
        ]
        ref = publish_snapshot(rows, tmp_path)

        content = _table_path(tmp_path, ref.dataset_snapshot_id).read_text(encoding="utf-8")
        restored = [GoldDistrictMonthlyMetrics.model_validate(json.loads(line)) for line in content.splitlines()]

        assert [(row.gu_code, row.period) for row in restored] == [
            ("11680", "2025-07"),
            ("11680", "2025-08"),
            ("11710", "2025-08"),
        ]

    def test_snapshot_id_is_deterministic_for_same_rows(self, tmp_path: Path) -> None:
        rows = [
            _make_gold(gu_code="11710", gu_name="송파구", period="2025-08"),
            _make_gold(gu_code="11680", gu_name="강남구", period="2025-07"),
        ]

        first = publish_snapshot(rows, tmp_path / "run-a")
        second = publish_snapshot(list(reversed(rows)), tmp_path / "run-b")

        assert first.dataset_snapshot_id == second.dataset_snapshot_id

    def test_republish_same_rows_preserves_existing_snapshot_metadata(self, tmp_path: Path) -> None:
        rows = [_make_gold(period="2025-07")]

        first = publish_snapshot(rows, tmp_path)
        first_manifest_path = _manifest_path(tmp_path, first.dataset_snapshot_id)
        first_created_at = json.loads(first_manifest_path.read_text(encoding="utf-8"))["created_at"]

        second = publish_snapshot(rows, tmp_path)
        second_created_at = json.loads(first_manifest_path.read_text(encoding="utf-8"))["created_at"]

        assert second.dataset_snapshot_id == first.dataset_snapshot_id
        assert second.created_at == first.created_at
        assert second_created_at == first_created_at

    def test_empty_rows_creates_empty_jsonl_and_zero_record_count(self, tmp_path: Path) -> None:
        ref = publish_snapshot([], tmp_path)

        assert _table_path(tmp_path, ref.dataset_snapshot_id).read_bytes() == b""
        manifest = SnapshotManifest.model_validate_json(
            _manifest_path(tmp_path, ref.dataset_snapshot_id).read_text(encoding="utf-8")
        )
        entry = manifest.get_table("gold_district_monthly_metrics")

        assert entry is not None
        assert entry.record_count == 0
        assert manifest.validate_integrity() is True

    def test_manifest_table_hash_matches_jsonl_file_bytes(self, tmp_path: Path) -> None:
        ref = publish_snapshot([_make_gold(), _make_gold(period="2025-08")], tmp_path)

        table_bytes = _table_path(tmp_path, ref.dataset_snapshot_id).read_bytes()
        manifest = SnapshotManifest.model_validate_json(
            _manifest_path(tmp_path, ref.dataset_snapshot_id).read_text(encoding="utf-8")
        )
        entry = manifest.get_table("gold_district_monthly_metrics")

        assert entry is not None
        assert entry.table_hash == hashlib.sha256(table_bytes).hexdigest()

    def test_manifest_sets_jsonl_file_format_and_schema_version(self, tmp_path: Path) -> None:
        ref = publish_snapshot([_make_gold()], tmp_path)
        manifest = SnapshotManifest.model_validate_json(
            _manifest_path(tmp_path, ref.dataset_snapshot_id).read_text(encoding="utf-8")
        )
        entry = manifest.get_table("gold_district_monthly_metrics")

        assert entry is not None
        assert entry.file_format == "jsonl"
        assert entry.schema_version == "1.0.0"

    def test_does_not_mutate_dataset_snapshot_id_on_input_rows(self, tmp_path: Path) -> None:
        row = _make_gold(dataset_snapshot_id="custom-row-id")

        publish_snapshot([row], tmp_path)

        assert row.dataset_snapshot_id == "custom-row-id"

    def test_supports_duplicate_rows(self, tmp_path: Path) -> None:
        row = _make_gold()
        ref = publish_snapshot([row, row], tmp_path)

        manifest = SnapshotManifest.model_validate_json(
            _manifest_path(tmp_path, ref.dataset_snapshot_id).read_text(encoding="utf-8")
        )
        _, restored = resolve_snapshot(ref.dataset_snapshot_id, tmp_path)

        entry = manifest.get_table("gold_district_monthly_metrics")
        assert entry is not None
        assert entry.record_count == 2
        assert restored == [row, row]

    def test_supports_single_row_publish(self, tmp_path: Path) -> None:
        row = _make_gold(gu_code="11470", gu_name="양천구")

        ref = publish_snapshot([row], tmp_path)
        _, restored = resolve_snapshot(ref.dataset_snapshot_id, tmp_path)

        assert restored == [row]

    def test_supports_special_characters_in_gu_name(self, tmp_path: Path) -> None:
        row = _make_gold(gu_name='종로구 "청계천" 🏙️ / 테스트')

        ref = publish_snapshot([row], tmp_path)
        _, restored = resolve_snapshot(ref.dataset_snapshot_id, tmp_path)

        assert restored[0].gu_name == '종로구 "청계천" 🏙️ / 테스트'


class TestResolveSnapshot:
    def test_resolve_by_explicit_snapshot_id(self, tmp_path: Path) -> None:
        rows = [_make_gold(period="2025-07"), _make_gold(period="2025-08")]
        ref = publish_snapshot(rows, tmp_path)

        manifest, restored = resolve_snapshot(ref.dataset_snapshot_id, tmp_path)

        assert manifest.dataset_snapshot_id == ref.dataset_snapshot_id
        assert restored == sorted(rows, key=lambda row: (row.gu_code, row.period))

    def test_resolve_latest_picks_manifest_with_newest_created_at(self, tmp_path: Path) -> None:
        first_ref = publish_snapshot([_make_gold(period="2025-07")], tmp_path)
        second_ref = publish_snapshot([_make_gold(period="2025-08")], tmp_path)

        first_manifest = _load_manifest(tmp_path, first_ref.dataset_snapshot_id)
        second_manifest = _load_manifest(tmp_path, second_ref.dataset_snapshot_id)
        first_manifest["created_at"] = "2026-03-29T00:00:00Z"
        second_manifest["created_at"] = "2026-03-30T00:00:00Z"
        _manifest_path(tmp_path, first_ref.dataset_snapshot_id).write_text(
            json.dumps(first_manifest, ensure_ascii=False),
            encoding="utf-8",
        )
        _manifest_path(tmp_path, second_ref.dataset_snapshot_id).write_text(
            json.dumps(second_manifest, ensure_ascii=False),
            encoding="utf-8",
        )

        manifest, rows = resolve_snapshot("latest", tmp_path)

        assert manifest.dataset_snapshot_id == second_ref.dataset_snapshot_id
        assert rows == sorted([_make_gold(period="2025-08")], key=lambda row: (row.gu_code, row.period))

    def test_resolve_latest_with_single_snapshot(self, tmp_path: Path) -> None:
        ref = publish_snapshot([_make_gold(period="2025-09")], tmp_path)

        manifest, rows = resolve_snapshot("latest", tmp_path)

        assert manifest.dataset_snapshot_id == ref.dataset_snapshot_id
        assert len(rows) == 1
        assert rows[0].period == "2025-09"

    def test_latest_raises_when_base_dir_has_no_snapshots(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            resolve_snapshot("latest", tmp_path)

    def test_explicit_snapshot_id_raises_when_directory_missing(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            resolve_snapshot("a" * 64, tmp_path)

    def test_explicit_snapshot_id_raises_when_manifest_missing(self, tmp_path: Path) -> None:
        snapshot_id = "b" * 64
        _snapshot_dir(tmp_path, snapshot_id).mkdir(parents=True)

        with pytest.raises(FileNotFoundError):
            resolve_snapshot(snapshot_id, tmp_path)

    def test_explicit_snapshot_id_raises_when_jsonl_missing(self, tmp_path: Path) -> None:
        ref = publish_snapshot([_make_gold()], tmp_path)
        _table_path(tmp_path, ref.dataset_snapshot_id).unlink()

        with pytest.raises(FileNotFoundError):
            resolve_snapshot(ref.dataset_snapshot_id, tmp_path)

    def test_latest_ignores_non_snapshot_directories_without_manifest(self, tmp_path: Path) -> None:
        (tmp_path / "misc").mkdir(parents=True)
        ref = publish_snapshot([_make_gold(period="2025-11")], tmp_path)

        manifest, rows = resolve_snapshot("latest", tmp_path)

        assert manifest.dataset_snapshot_id == ref.dataset_snapshot_id
        assert rows[0].period == "2025-11"


class TestResolveSnapshotIntegrity:
    def test_detects_tampered_jsonl_content_hash_mismatch(self, tmp_path: Path) -> None:
        ref = publish_snapshot([_make_gold()], tmp_path)
        table_file = _table_path(tmp_path, ref.dataset_snapshot_id)
        table_file.write_text(table_file.read_text(encoding="utf-8") + '{"tampered":true}\n', encoding="utf-8")

        with pytest.raises(ValueError, match="Table hash mismatch"):
            resolve_snapshot(ref.dataset_snapshot_id, tmp_path)

    def test_detects_tampered_manifest_table_hash_integrity_failure(self, tmp_path: Path) -> None:
        ref = publish_snapshot([_make_gold()], tmp_path)
        payload = _load_manifest(tmp_path, ref.dataset_snapshot_id)
        payload["table_entries"][0]["table_hash"] = "f" * 64
        _manifest_path(tmp_path, ref.dataset_snapshot_id).write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="Manifest integrity check failed"):
            resolve_snapshot(ref.dataset_snapshot_id, tmp_path)

    def test_detects_tampered_manifest_dataset_snapshot_id_integrity_failure(self, tmp_path: Path) -> None:
        ref = publish_snapshot([_make_gold()], tmp_path)
        payload = _load_manifest(tmp_path, ref.dataset_snapshot_id)
        payload["dataset_snapshot_id"] = "a" * 64
        _manifest_path(tmp_path, ref.dataset_snapshot_id).write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="Manifest integrity check failed"):
            resolve_snapshot(ref.dataset_snapshot_id, tmp_path)

    def test_corrupt_manifest_json_raises_value_error(self, tmp_path: Path) -> None:
        ref = publish_snapshot([_make_gold()], tmp_path)
        _manifest_path(tmp_path, ref.dataset_snapshot_id).write_text("{not-json", encoding="utf-8")

        with pytest.raises(ValueError, match="Invalid manifest JSON"):
            resolve_snapshot(ref.dataset_snapshot_id, tmp_path)

    def test_manifest_missing_required_table_entry_raises_value_error(self, tmp_path: Path) -> None:
        content = _make_jsonl_bytes([_make_gold()])
        table_hash = hashlib.sha256(content).hexdigest()
        manifest = SnapshotManifest(
            dataset_snapshot_id=SnapshotManifest.compute_snapshot_id({"other_table": table_hash}),
            created_at=datetime(2026, 3, 29, 12, 0, tzinfo=timezone.utc),
            table_entries=[
                SnapshotTableEntry(
                    table_name="other_table",
                    table_hash=table_hash,
                    record_count=1,
                    schema_version="1.0.0",
                    file_format="jsonl",
                )
            ],
        )

        snapshot_dir = tmp_path / manifest.dataset_snapshot_id
        snapshot_dir.mkdir(parents=True)
        (snapshot_dir / "gold_district_monthly_metrics.jsonl").write_bytes(content)
        (snapshot_dir / "manifest.json").write_text(manifest.model_dump_json(), encoding="utf-8")

        with pytest.raises(ValueError, match="Manifest missing table entry"):
            resolve_snapshot(manifest.dataset_snapshot_id, tmp_path)

    def test_invalid_jsonl_row_content_raises_value_error(self, tmp_path: Path) -> None:
        invalid_content = b'{"gu_code": "11680", "period": "2025-07"}\n'
        snapshot_id = _write_manual_snapshot(
            tmp_path,
            content=invalid_content,
            created_at=datetime(2026, 3, 29, 12, 0, tzinfo=timezone.utc),
        )

        with pytest.raises(ValueError, match="Invalid gold row content"):
            resolve_snapshot(snapshot_id, tmp_path)

    def test_latest_raises_when_only_non_snapshot_directories_exist(self, tmp_path: Path) -> None:
        (tmp_path / "dir-a").mkdir(parents=True)
        (tmp_path / "dir-b").mkdir(parents=True)

        with pytest.raises(FileNotFoundError):
            resolve_snapshot("latest", tmp_path)

    def test_latest_raises_for_invalid_manifest_schema(self, tmp_path: Path) -> None:
        snapshot_dir = tmp_path / "invalid-manifest"
        snapshot_dir.mkdir(parents=True)
        (snapshot_dir / "manifest.json").write_text("{}", encoding="utf-8")

        with pytest.raises(ValueError, match="Invalid manifest schema"):
            resolve_snapshot("latest", tmp_path)
