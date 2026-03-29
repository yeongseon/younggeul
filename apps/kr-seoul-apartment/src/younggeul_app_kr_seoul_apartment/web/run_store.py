from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel


class RunMeta(BaseModel):
    run_id: str
    query: str
    status: str
    created_at: datetime
    completed_at: datetime | None = None
    error: str | None = None


class RunStore:
    def __init__(self, base_dir: Path | str = Path("./output/runs")) -> None:
        self.base_dir = Path(base_dir)

    def create_run(self, query: str) -> str:
        run_id = str(uuid4())
        run_dir = self.base_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=False)

        meta = RunMeta(
            run_id=run_id,
            query=query,
            status="pending",
            created_at=datetime.now(timezone.utc),
        )
        self._write_meta(run_id, meta)
        return run_id

    def update_status(
        self,
        run_id: str,
        status: str,
        *,
        error: str | None = None,
        report: str | None = None,
    ) -> None:
        meta = self._read_meta(run_id)
        completed_at = meta.completed_at
        if status in {"completed", "failed"}:
            completed_at = datetime.now(timezone.utc)

        updated = meta.model_copy(update={"status": status, "error": error, "completed_at": completed_at})
        self._write_meta(run_id, updated)

        if report is not None:
            self._report_path(run_id).write_text(report, encoding="utf-8")

    def get_run(self, run_id: str) -> RunMeta | None:
        meta_path = self._meta_path(run_id)
        if not meta_path.exists():
            return None
        return RunMeta.model_validate_json(meta_path.read_text(encoding="utf-8"))

    def list_runs(self) -> list[RunMeta]:
        if not self.base_dir.exists():
            return []

        runs: list[RunMeta] = []
        for run_dir in self.base_dir.iterdir():
            if not run_dir.is_dir():
                continue
            meta_path = run_dir / "meta.json"
            if not meta_path.exists():
                continue
            runs.append(RunMeta.model_validate_json(meta_path.read_text(encoding="utf-8")))

        return sorted(runs, key=lambda meta: meta.created_at, reverse=True)

    def _meta_path(self, run_id: str) -> Path:
        return self.base_dir / run_id / "meta.json"

    def _report_path(self, run_id: str) -> Path:
        return self.base_dir / run_id / "report.md"

    def _write_meta(self, run_id: str, meta: RunMeta) -> None:
        meta_path = self._meta_path(run_id)
        temp_path = meta_path.with_suffix(".tmp")
        payload = json.dumps(meta.model_dump(mode="json"), ensure_ascii=False)
        temp_path.write_text(payload, encoding="utf-8")
        temp_path.replace(meta_path)

    def _read_meta(self, run_id: str) -> RunMeta:
        meta_path = self._meta_path(run_id)
        return RunMeta.model_validate_json(meta_path.read_text(encoding="utf-8"))
