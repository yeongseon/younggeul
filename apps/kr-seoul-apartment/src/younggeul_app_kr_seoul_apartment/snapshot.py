"""Snapshot publishing and resolution helpers for Gold district metrics."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from younggeul_core.state.gold import GoldDistrictMonthlyMetrics
from younggeul_core.state.simulation import SnapshotRef
from younggeul_core.storage.snapshot import SnapshotManifest, SnapshotTableEntry

_TABLE_NAME = "gold_district_monthly_metrics"
_TABLE_FILE_NAME = "gold_district_monthly_metrics.jsonl"
_MANIFEST_FILE_NAME = "manifest.json"


def _sorted_gold_rows(gold_rows: list[GoldDistrictMonthlyMetrics]) -> list[GoldDistrictMonthlyMetrics]:
    return sorted(gold_rows, key=lambda row: (row.gu_code, row.period))


def _jsonl_bytes(gold_rows: list[GoldDistrictMonthlyMetrics]) -> bytes:
    if not gold_rows:
        return b""
    lines = [row.model_dump_json().encode("utf-8") for row in gold_rows]
    return b"\n".join(lines) + b"\n"


def _load_manifest(manifest_path: Path) -> SnapshotManifest:
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError(f"Invalid manifest JSON at {manifest_path}") from exc

    try:
        manifest = SnapshotManifest.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"Invalid manifest schema at {manifest_path}") from exc

    if not manifest.validate_integrity():
        raise ValueError(f"Manifest integrity check failed at {manifest_path}")

    return manifest


def publish_snapshot(gold_rows: list[GoldDistrictMonthlyMetrics], base_dir: Path) -> SnapshotRef:
    """Publish Gold metrics as an immutable dataset snapshot.

    Args:
        gold_rows: Gold district monthly metric rows to persist.
        base_dir: Root directory where snapshot folders are stored.

    Returns:
        Reference metadata for the newly published snapshot.
    """
    sorted_rows = _sorted_gold_rows(gold_rows)
    jsonl_content = _jsonl_bytes(sorted_rows)
    table_hash = hashlib.sha256(jsonl_content).hexdigest()
    dataset_snapshot_id = SnapshotManifest.compute_snapshot_id({_TABLE_NAME: table_hash})

    snapshot_dir = base_dir / dataset_snapshot_id
    manifest_path = snapshot_dir / _MANIFEST_FILE_NAME
    table_path = snapshot_dir / _TABLE_FILE_NAME
    if snapshot_dir.exists():
        manifest = _load_manifest(manifest_path)
        table_entry = manifest.get_table(_TABLE_NAME)
        if table_entry is None:
            raise ValueError(f"Manifest missing table entry: {_TABLE_NAME}")

        existing_table_bytes = table_path.read_bytes()
        if existing_table_bytes != jsonl_content:
            raise ValueError(f"Snapshot already exists with different content: {dataset_snapshot_id}")

        existing_table_hash = hashlib.sha256(existing_table_bytes).hexdigest()
        if existing_table_hash != table_entry.table_hash:
            raise ValueError(f"Existing snapshot content failed integrity check: {dataset_snapshot_id}")

        return SnapshotRef(
            dataset_snapshot_id=manifest.dataset_snapshot_id,
            created_at=manifest.created_at,
            table_count=len(manifest.table_entries),
        )

    snapshot_dir.mkdir(parents=True, exist_ok=False)

    table_path.write_bytes(jsonl_content)

    created_at = datetime.now(timezone.utc)
    manifest = SnapshotManifest(
        dataset_snapshot_id=dataset_snapshot_id,
        created_at=created_at,
        table_entries=[
            SnapshotTableEntry(
                table_name=_TABLE_NAME,
                table_hash=table_hash,
                record_count=len(sorted_rows),
                schema_version="1.0.0",
                file_format="jsonl",
            )
        ],
    )

    manifest_path.write_text(manifest.model_dump_json(), encoding="utf-8")

    return SnapshotRef(
        dataset_snapshot_id=dataset_snapshot_id,
        created_at=created_at,
        table_count=1,
    )


def resolve_snapshot(snapshot_id: str, base_dir: Path) -> tuple[SnapshotManifest, list[GoldDistrictMonthlyMetrics]]:
    """Resolve a snapshot manifest and its Gold rows.

    Args:
        snapshot_id: Snapshot identifier or ``"latest"``.
        base_dir: Root directory containing snapshot folders.

    Returns:
        The validated snapshot manifest and parsed Gold metric rows.

    Raises:
        FileNotFoundError: If the requested snapshot cannot be found.
        ValueError: If manifest or table integrity checks fail.
    """
    if snapshot_id == "latest":
        latest_manifest: SnapshotManifest | None = None
        latest_snapshot_dir: Path | None = None

        for candidate in base_dir.iterdir():
            if not candidate.is_dir():
                continue
            manifest_path = candidate / _MANIFEST_FILE_NAME
            if not manifest_path.exists():
                continue
            manifest = _load_manifest(manifest_path)
            if latest_manifest is None or manifest.created_at > latest_manifest.created_at:
                latest_manifest = manifest
                latest_snapshot_dir = candidate

        if latest_manifest is None or latest_snapshot_dir is None:
            raise FileNotFoundError(f"No snapshots found in {base_dir}")

        manifest = latest_manifest
        snapshot_dir = latest_snapshot_dir
    else:
        snapshot_dir = base_dir / snapshot_id
        if not snapshot_dir.exists():
            raise FileNotFoundError(f"Snapshot directory not found: {snapshot_dir}")

        manifest = _load_manifest(snapshot_dir / _MANIFEST_FILE_NAME)

    table_entry = manifest.get_table(_TABLE_NAME)
    if table_entry is None:
        raise ValueError(f"Manifest missing table entry: {_TABLE_NAME}")

    table_path = snapshot_dir / _TABLE_FILE_NAME
    table_content = table_path.read_bytes()
    computed_hash = hashlib.sha256(table_content).hexdigest()
    if computed_hash != table_entry.table_hash:
        raise ValueError(f"Table hash mismatch for {_TABLE_NAME}")

    decoded = table_content.decode("utf-8")
    rows: list[GoldDistrictMonthlyMetrics] = []
    for line in decoded.splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSONL content at {table_path}") from exc
        try:
            rows.append(GoldDistrictMonthlyMetrics.model_validate(payload))
        except ValidationError as exc:
            raise ValueError(f"Invalid gold row content at {table_path}") from exc

    return manifest, rows
