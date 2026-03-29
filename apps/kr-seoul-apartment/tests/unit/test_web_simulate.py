from __future__ import annotations

import time
from importlib import import_module
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from younggeul_app_kr_seoul_apartment.web.run_store import RunStore

web_app = import_module("younggeul_app_kr_seoul_apartment.web.app")
simulate_routes = import_module("younggeul_app_kr_seoul_apartment.web.routes.simulate")


def _create_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    runs_dir = tmp_path / "runs"

    def run_store_factory(base_dir: Path | str | None = None) -> RunStore:
        _ = base_dir
        return RunStore(base_dir=runs_dir)

    monkeypatch.setattr(web_app, "RunStore", run_store_factory)
    return TestClient(web_app.create_app())


def test_post_simulate_returns_202_with_run_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_background(*args: object, **kwargs: object) -> None:
        _ = (args, kwargs)

    monkeypatch.setattr(simulate_routes, "run_simulation_background", fake_background)

    with _create_client(tmp_path, monkeypatch) as client:
        response = client.post("/simulate", json={"query": "강남구"})

        assert response.status_code == 202
        payload = response.json()
        assert payload["run_id"]
        assert payload["status"] == "pending"


def test_post_simulate_accepts_valid_model_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_background(*args: object, **kwargs: object) -> None:
        _ = (args, kwargs)

    monkeypatch.setattr(simulate_routes, "run_simulation_background", fake_background)

    with _create_client(tmp_path, monkeypatch) as client:
        response = client.post(
            "/simulate",
            json={"query": "강남구", "max_rounds": 3, "model_id": "gpt-4o-mini"},
        )

        assert response.status_code == 202


def test_post_simulate_rejects_invalid_model_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_background(*args: object, **kwargs: object) -> None:
        _ = (args, kwargs)

    monkeypatch.setattr(simulate_routes, "run_simulation_background", fake_background)

    with _create_client(tmp_path, monkeypatch) as client:
        response = client.post(
            "/simulate",
            json={"query": "강남구", "max_rounds": 3, "model_id": "unknown-model"},
        )

        assert response.status_code == 422
        assert "model_id 'unknown-model' is not allowed" in response.text


def test_post_simulate_rejects_max_rounds_over_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_background(*args: object, **kwargs: object) -> None:
        _ = (args, kwargs)

    monkeypatch.setattr(simulate_routes, "run_simulation_background", fake_background)

    with _create_client(tmp_path, monkeypatch) as client:
        response = client.post(
            "/simulate",
            json={"query": "강남구", "max_rounds": 11, "model_id": "stub"},
        )

        assert response.status_code == 422
        assert "max_rounds must be between 1 and 10" in response.text


def test_post_simulate_rejects_max_rounds_below_one(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_background(*args: object, **kwargs: object) -> None:
        _ = (args, kwargs)

    monkeypatch.setattr(simulate_routes, "run_simulation_background", fake_background)

    with _create_client(tmp_path, monkeypatch) as client:
        response = client.post(
            "/simulate",
            json={"query": "강남구", "max_rounds": 0, "model_id": "stub"},
        )

        assert response.status_code == 422
        assert "max_rounds must be between 1 and 10" in response.text


def test_post_simulate_respects_allowed_models_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_background(*args: object, **kwargs: object) -> None:
        _ = (args, kwargs)

    monkeypatch.setattr(simulate_routes, "run_simulation_background", fake_background)
    monkeypatch.setenv("YOUNGGEUL_ALLOWED_MODELS", "custom-model")

    with _create_client(tmp_path, monkeypatch) as client:
        accepted_response = client.post(
            "/simulate",
            json={"query": "강남구", "max_rounds": 3, "model_id": "custom-model"},
        )
        rejected_response = client.post(
            "/simulate",
            json={"query": "강남구", "max_rounds": 3, "model_id": "stub"},
        )

        assert accepted_response.status_code == 202
        assert rejected_response.status_code == 422


def test_get_simulate_by_run_id_returns_status(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_background(*args: object, **kwargs: object) -> None:
        _ = (args, kwargs)

    monkeypatch.setattr(simulate_routes, "run_simulation_background", fake_background)

    with _create_client(tmp_path, monkeypatch) as client:
        start_response = client.post("/simulate", json={"query": "송파구"})
        run_id = start_response.json()["run_id"]

        response = client.get(f"/simulate/{run_id}")

        assert response.status_code == 200
        payload = response.json()
        assert payload["run_id"] == run_id
        assert payload["query"] == "송파구"
        assert payload["status"] == "pending"


def test_get_simulate_by_unknown_run_id_returns_404(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with _create_client(tmp_path, monkeypatch) as client:
        response = client.get("/simulate/does-not-exist")

        assert response.status_code == 404
        assert response.json()["detail"] == "Run not found"


def test_get_simulate_lists_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_background(*args: object, **kwargs: object) -> None:
        _ = (args, kwargs)

    monkeypatch.setattr(simulate_routes, "run_simulation_background", fake_background)

    with _create_client(tmp_path, monkeypatch) as client:
        first_run_id = client.post("/simulate", json={"query": "first"}).json()["run_id"]
        second_run_id = client.post("/simulate", json={"query": "second"}).json()["run_id"]

        response = client.get("/simulate")

        assert response.status_code == 200
        payload = response.json()
        run_ids = {run["run_id"] for run in payload}
        assert first_run_id in run_ids
        assert second_run_id in run_ids


def test_full_background_simulation_lifecycle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_background(run_store: RunStore, run_id: str, query: str, max_rounds: int, model_id: str) -> None:
        _ = (query, max_rounds, model_id)
        run_store.update_status(run_id, "running")
        time.sleep(0.02)
        run_store.update_status(run_id, "completed", report="# Simulation Report")

    monkeypatch.setattr(simulate_routes, "run_simulation_background", fake_background)

    with _create_client(tmp_path, monkeypatch) as client:
        start_response = client.post("/simulate", json={"query": "마포구", "max_rounds": 1, "model_id": "stub"})
        run_id = start_response.json()["run_id"]

        final_payload: dict[str, object] = {}
        for _ in range(30):
            poll_response = client.get(f"/simulate/{run_id}")
            final_payload = poll_response.json()
            if final_payload["status"] in {"completed", "failed"}:
                break
            time.sleep(0.01)

        assert final_payload["status"] == "completed"


def test_post_simulate_marks_failed_when_executor_submit_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FailingExecutor:
        def __init__(self, max_workers: int) -> None:
            _ = max_workers

        def submit(self, *args: object, **kwargs: object) -> None:
            _ = (args, kwargs)
            raise RuntimeError("executor unavailable")

        def shutdown(self, wait: bool = True) -> None:
            _ = wait

    monkeypatch.setattr(web_app, "ThreadPoolExecutor", FailingExecutor)

    with _create_client(tmp_path, monkeypatch) as client:
        response = client.post("/simulate", json={"query": "강남구"})

    assert response.status_code == 500
    assert response.json() == {"detail": "executor unavailable"}

    store = RunStore(base_dir=tmp_path / "runs")
    runs = store.list_runs()
    assert len(runs) == 1
    assert runs[0].status == "failed"
    assert runs[0].error == "executor unavailable"
