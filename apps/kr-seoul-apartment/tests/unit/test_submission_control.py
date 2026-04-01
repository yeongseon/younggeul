from __future__ import annotations

from datetime import datetime, timezone

import pytest

from younggeul_app_kr_seoul_apartment.web.run_store import RunMeta
from younggeul_app_kr_seoul_apartment.web.submission_control import has_submission_capacity, inflight_run_count


class _FakeRunStore:
    def __init__(self, runs: list[RunMeta]) -> None:
        self._runs = runs

    def list_runs(self) -> list[RunMeta]:
        return self._runs


@pytest.fixture
def sample_run_meta() -> RunMeta:
    return RunMeta(
        run_id="pending",
        query="강남구",
        status="pending",
        created_at=datetime.now(timezone.utc),
    )


def test_inflight_run_count_only_includes_pending_and_running(sample_run_meta: RunMeta) -> None:
    completed = sample_run_meta.model_copy(update={"run_id": "completed", "status": "completed"})
    failed = sample_run_meta.model_copy(update={"run_id": "failed", "status": "failed"})
    store = _FakeRunStore([sample_run_meta, completed, failed])

    assert inflight_run_count(store) == 1


def test_has_submission_capacity_rejects_when_limit_is_reached(monkeypatch, sample_run_meta: RunMeta) -> None:
    pending = sample_run_meta
    running = sample_run_meta.model_copy(update={"run_id": "running", "status": "running"})
    store = _FakeRunStore([pending, running])
    monkeypatch.setenv("YOUNGGEUL_WEB_MAX_INFLIGHT_RUNS", "2")

    assert has_submission_capacity(store) is False


def test_has_submission_capacity_accepts_when_under_limit(monkeypatch, sample_run_meta: RunMeta) -> None:
    store = _FakeRunStore([sample_run_meta])
    monkeypatch.setenv("YOUNGGEUL_WEB_MAX_INFLIGHT_RUNS", "2")

    assert has_submission_capacity(store) is True
