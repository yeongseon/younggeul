from __future__ import annotations

from typing import Protocol

from .config import get_max_inflight_runs
from .run_store import RunMeta

_INFLIGHT_STATUSES = frozenset({"pending", "running"})


class RunStoreLike(Protocol):
    def list_runs(self) -> list[RunMeta]: ...


def inflight_run_count(run_store: RunStoreLike) -> int:
    return sum(1 for run in run_store.list_runs() if run.status in _INFLIGHT_STATUSES)


def has_submission_capacity(run_store: RunStoreLike) -> bool:
    return inflight_run_count(run_store) < get_max_inflight_runs()
