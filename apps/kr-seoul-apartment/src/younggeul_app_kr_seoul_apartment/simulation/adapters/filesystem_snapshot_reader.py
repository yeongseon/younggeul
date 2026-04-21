from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

from pydantic import ValidationError

from younggeul_core.state.gold import BaselineForecast, GoldDistrictMonthlyMetrics
from younggeul_core.state.simulation import SnapshotRef
from younggeul_core.storage.snapshot import SnapshotManifest

from ..ports.snapshot_reader import SnapshotCoverage, SnapshotReader

_TABLE_FILE_NAME = "gold_district_monthly_metrics.jsonl"
_MANIFEST_FILE_NAME = "manifest.json"
_BASELINE_REPORT_GLOB = "baseline_report_*.json"


class FilesystemSnapshotReader(SnapshotReader):
    """Read simulation snapshot inputs from local filesystem directories.

    The reader resolves one published dataset snapshot under ``snapshot_dir`` and,
    when available, baseline forecast reports under ``baseline_dir``. Parsed data
    is cached per instance to avoid repeated disk reads within one CLI invocation.

    Args:
        snapshot_dir: Root directory containing snapshot subdirectories keyed by
            ``dataset_snapshot_id``.
        baseline_dir: Optional directory containing ``baseline_report_*.json``
            files produced by the baseline CLI.
    """

    def __init__(self, snapshot_dir: Path, baseline_dir: Path | None = None) -> None:
        self._snapshot_dir = snapshot_dir
        self._baseline_dir = baseline_dir
        self._manifest_cache: dict[str, SnapshotManifest] = {}
        self._metrics_cache: dict[str, list[GoldDistrictMonthlyMetrics]] = {}
        self._baseline_cache: dict[str, list[BaselineForecast]] = {}
        self._baseline_payload_cache: dict[Path, dict[str, Any]] = {}

    def get_coverage(self, snapshot: SnapshotRef) -> SnapshotCoverage:
        """Return available geography and period coverage for a snapshot.

        Args:
            snapshot: Snapshot reference to inspect.

        Returns:
            Coverage metadata derived from the manifest and gold JSONL rows.

        Raises:
            ValueError: If the snapshot manifest or gold rows are invalid.
        """
        manifest = self._load_manifest(snapshot)
        rows = self._load_metrics(snapshot)
        if not rows:
            raise ValueError(f"Snapshot contains no gold metrics rows: {snapshot.dataset_snapshot_id}")

        available_gu_names = {row.gu_code: row.gu_name for row in rows}
        periods = [row.period for row in rows]
        record_count = sum(entry.record_count for entry in manifest.table_entries)
        return SnapshotCoverage(
            available_gu_codes=sorted(available_gu_names),
            available_gu_names=available_gu_names,
            min_period=min(periods),
            max_period=max(periods),
            record_count=record_count,
        )

    def get_latest_metrics(
        self,
        snapshot: SnapshotRef,
        gu_codes: Sequence[str] | None = None,
    ) -> list[GoldDistrictMonthlyMetrics]:
        """Return latest district metrics for selected districts.

        Args:
            snapshot: Snapshot reference to read from.
            gu_codes: Optional district codes to filter by.

        Returns:
            Latest-period metric row for each requested district.

        Raises:
            ValueError: If the snapshot gold JSONL content is invalid.
        """
        rows = self._load_metrics(snapshot)
        requested_codes = None if gu_codes is None else set(gu_codes)

        latest_by_gu: dict[str, GoldDistrictMonthlyMetrics] = {}
        for row in rows:
            if requested_codes is not None and row.gu_code not in requested_codes:
                continue
            current = latest_by_gu.get(row.gu_code)
            if current is None or row.period > current.period:
                latest_by_gu[row.gu_code] = row

        return [latest_by_gu[gu_code] for gu_code in sorted(latest_by_gu)]

    def get_baseline_forecasts(
        self,
        snapshot: SnapshotRef,
        gu_codes: Sequence[str] | None = None,
    ) -> list[BaselineForecast]:
        """Return baseline forecasts for selected districts.

        Args:
            snapshot: Snapshot reference to read from.
            gu_codes: Optional district codes to filter by.

        Returns:
            Matching baseline forecasts, or an empty list when no baseline report
            exists for the snapshot.

        Raises:
            ValueError: If a matching baseline report has invalid JSON or schema.
        """
        forecasts = list(self._load_baselines(snapshot))
        if gu_codes is None:
            return forecasts

        requested_codes = set(gu_codes)
        return [forecast for forecast in forecasts if forecast.gu_code in requested_codes]

    def _load_manifest(self, snapshot: SnapshotRef) -> SnapshotManifest:
        snapshot_id = snapshot.dataset_snapshot_id
        cached = self._manifest_cache.get(snapshot_id)
        if cached is not None:
            return cached

        manifest_path = self._snapshot_dir / snapshot_id / _MANIFEST_FILE_NAME
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ValueError(f"Snapshot manifest not found: {manifest_path}") from exc
        except (json.JSONDecodeError, OSError) as exc:
            raise ValueError(f"Invalid manifest JSON at {manifest_path}") from exc

        try:
            manifest = SnapshotManifest.model_validate(payload)
        except ValidationError as exc:
            raise ValueError(f"Invalid manifest schema at {manifest_path}") from exc

        if manifest.dataset_snapshot_id != snapshot_id:
            raise ValueError(
                f"Snapshot manifest id mismatch at {manifest_path}: {manifest.dataset_snapshot_id} != {snapshot_id}"
            )

        self._manifest_cache[snapshot_id] = manifest
        return manifest

    def _load_metrics(self, snapshot: SnapshotRef) -> list[GoldDistrictMonthlyMetrics]:
        snapshot_id = snapshot.dataset_snapshot_id
        cached = self._metrics_cache.get(snapshot_id)
        if cached is not None:
            return cached

        table_path = self._snapshot_dir / snapshot_id / _TABLE_FILE_NAME
        try:
            lines = table_path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError as exc:
            raise ValueError(f"Snapshot gold JSONL not found: {table_path}") from exc
        except OSError as exc:
            raise ValueError(f"Unable to read snapshot gold JSONL at {table_path}") from exc

        rows: list[GoldDistrictMonthlyMetrics] = []
        for line in lines:
            if not line.strip():
                continue
            try:
                rows.append(GoldDistrictMonthlyMetrics.model_validate_json(line))
            except ValidationError as exc:
                raise ValueError(f"Invalid gold JSONL content in {table_path}") from exc

        self._metrics_cache[snapshot_id] = rows
        return rows

    def _load_baselines(self, snapshot: SnapshotRef) -> list[BaselineForecast]:
        snapshot_id = snapshot.dataset_snapshot_id
        cached = self._baseline_cache.get(snapshot_id)
        if cached is not None:
            return cached

        if self._baseline_dir is None:
            self._baseline_cache[snapshot_id] = []
            return []

        matching_reports: list[Path] = []
        for report_path in sorted(self._baseline_dir.glob(_BASELINE_REPORT_GLOB)):
            payload = self._load_baseline_payload(report_path)
            snapshot_payload = payload.get("snapshot")
            if not isinstance(snapshot_payload, dict):
                continue
            if snapshot_payload.get("dataset_snapshot_id") == snapshot_id:
                matching_reports.append(report_path)

        if not matching_reports:
            self._baseline_cache[snapshot_id] = []
            return []

        latest_report = max(matching_reports, key=lambda path: path.stat().st_mtime_ns)
        payload = self._load_baseline_payload(latest_report)
        forecasts_payload = payload.get("forecasts")
        if not isinstance(forecasts_payload, list):
            raise ValueError(f"Invalid baseline report schema at {latest_report}")

        forecasts: list[BaselineForecast] = []
        for item in forecasts_payload:
            try:
                forecasts.append(BaselineForecast.model_validate(item))
            except ValidationError as exc:
                raise ValueError(f"Invalid baseline forecast content in {latest_report}") from exc

        self._baseline_cache[snapshot_id] = forecasts
        return forecasts

    def _load_baseline_payload(self, report_path: Path) -> dict[str, Any]:
        cached = self._baseline_payload_cache.get(report_path)
        if cached is not None:
            return cached

        try:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise ValueError(f"Invalid baseline report JSON at {report_path}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"Invalid baseline report schema at {report_path}")

        self._baseline_payload_cache[report_path] = payload
        return payload
