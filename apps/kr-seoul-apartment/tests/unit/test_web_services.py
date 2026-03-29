from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from younggeul_app_kr_seoul_apartment.pipeline import BronzeInput
from younggeul_app_kr_seoul_apartment.simulation.event_store import InMemoryEventStore
from younggeul_app_kr_seoul_apartment.web import services
from younggeul_app_kr_seoul_apartment.web.run_store import RunStore


def test_run_pipeline_service_passes_through(monkeypatch: pytest.MonkeyPatch) -> None:
    bronze = BronzeInput(apt_transactions=[], interest_rates=[], migrations=[])

    def fake_run_pipeline(arg: BronzeInput) -> str:
        assert arg is bronze
        return "ok"

    monkeypatch.setattr(services, "run_pipeline", fake_run_pipeline)
    assert services.run_pipeline_service(bronze) == "ok"


def test_publish_snapshot_service_passes_through(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    payload = object()

    def fake_publish_snapshot(gold_rows: list[Any], base_dir: Path) -> object:
        assert gold_rows == []
        assert base_dir == tmp_path
        return payload

    monkeypatch.setattr(services, "publish_snapshot", fake_publish_snapshot)
    assert services.publish_snapshot_service([], tmp_path) is payload


def test_resolve_snapshot_service_passes_through(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    payload = (object(), [])

    def fake_resolve_snapshot(snapshot_id: str, base_dir: Path) -> tuple[object, list[Any]]:
        assert snapshot_id == "latest"
        assert base_dir == tmp_path
        return payload

    monkeypatch.setattr(services, "resolve_snapshot", fake_resolve_snapshot)
    assert services.resolve_snapshot_service("latest", tmp_path) == payload


def test_forecast_baseline_service_passes_through(monkeypatch: pytest.MonkeyPatch) -> None:
    payload: list[object] = [object()]

    def fake_forecast_baseline(metrics: list[Any]) -> list[object]:
        assert metrics == []
        return payload

    monkeypatch.setattr(services, "forecast_baseline", fake_forecast_baseline)
    assert services.forecast_baseline_service([]) == payload


def test_build_simulation_graph_service_passes_through(monkeypatch: pytest.MonkeyPatch) -> None:
    event_store = InMemoryEventStore()
    payload = object()

    def fake_build_simulation_graph(arg: object) -> object:
        assert arg is event_store
        return payload

    monkeypatch.setattr(services, "build_simulation_graph", fake_build_simulation_graph)
    assert services.build_simulation_graph_service(event_store) is payload


def test_seed_graph_state_service_passes_through(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"event_refs": []}

    def fake_seed_graph_state(user_query: str, run_id: str, run_name: str, model_id: str) -> dict[str, list[str]]:
        assert user_query == "q"
        assert run_id == "r"
        assert run_name == "name"
        assert model_id == "model"
        return payload

    monkeypatch.setattr(services, "seed_graph_state", fake_seed_graph_state)
    assert services.seed_graph_state_service("q", "r", "name", "model") == payload


def test_run_simulation_background_completes_and_writes_report(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    store = RunStore(base_dir=tmp_path)
    run_id = store.create_run("q")

    class FakeGraph:
        def invoke(self, initial_state: dict[str, object]) -> dict[str, object]:
            assert initial_state["max_rounds"] == 2
            return {
                "rendered_report": {
                    "run_id": run_id,
                    "round_no": 2,
                    "rendered_at": datetime.now(timezone.utc).isoformat(),
                    "total_claims": 1,
                    "passed_claims": 1,
                    "failed_claims": 0,
                    "sections": [],
                    "markdown": "# Simulation Report\n\nOK",
                }
            }

    monkeypatch.setattr(services, "build_simulation_graph", lambda *_args, **_kwargs: FakeGraph())

    services.run_simulation_background(store, run_id, "query", 2, "stub")

    run_meta = store.get_run(run_id)
    assert run_meta is not None
    assert run_meta.status == "completed"
    assert run_meta.completed_at is not None
    report_file = tmp_path / run_id / "report.md"
    assert report_file.read_text(encoding="utf-8") == "# Simulation Report\n\nOK"


def test_run_simulation_background_marks_failed_on_exception(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    store = RunStore(base_dir=tmp_path)
    run_id = store.create_run("q")

    class FakeGraph:
        def invoke(self, initial_state: dict[str, object]) -> dict[str, object]:
            _ = initial_state
            raise RuntimeError("boom")

    monkeypatch.setattr(services, "build_simulation_graph", lambda *_args, **_kwargs: FakeGraph())

    services.run_simulation_background(store, run_id, "query", 3, "stub")

    run_meta = store.get_run(run_id)
    assert run_meta is not None
    assert run_meta.status == "failed"
    assert run_meta.error is not None
    assert "boom" in run_meta.error
