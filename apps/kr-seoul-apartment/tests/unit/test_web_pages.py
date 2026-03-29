from __future__ import annotations

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


def test_get_ui_dashboard_returns_html(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with _create_client(tmp_path, monkeypatch) as client:
        response = client.get("/ui/dashboard")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "시뮬레이션 대시보드" in response.text


def test_get_ui_simulate_returns_html(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with _create_client(tmp_path, monkeypatch) as client:
        response = client.get("/ui/simulate")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "시뮬레이션 실행" in response.text


def test_get_ui_baseline_returns_html(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with _create_client(tmp_path, monkeypatch) as client:
        response = client.get("/ui/baseline")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Baseline Forecast" in response.text


def test_get_ui_simulate_run_detail_returns_200_for_existing_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_background(*args: object, **kwargs: object) -> None:
        _ = (args, kwargs)

    monkeypatch.setattr(simulate_routes, "run_simulation_background", fake_background)

    with _create_client(tmp_path, monkeypatch) as client:
        run_id = client.post("/simulate", json={"query": "강남구"}).json()["run_id"]
        response = client.get(f"/ui/simulate/{run_id}")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert run_id in response.text


def test_get_ui_simulate_run_detail_returns_404_for_missing_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _create_client(tmp_path, monkeypatch) as client:
        response = client.get("/ui/simulate/does-not-exist")

    assert response.status_code == 404
    assert response.json()["detail"] == "Run not found"


def test_get_ui_partials_runs_returns_html_fragment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_background(*args: object, **kwargs: object) -> None:
        _ = (args, kwargs)

    monkeypatch.setattr(simulate_routes, "run_simulation_background", fake_background)

    with _create_client(tmp_path, monkeypatch) as client:
        _ = client.post("/simulate", json={"query": "송파구"})
        response = client.get("/ui/partials/runs")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<tr>" in response.text


def test_post_ui_simulate_rejects_invalid_model_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with _create_client(tmp_path, monkeypatch) as client:
        response = client.post(
            "/ui/simulate",
            data={"query": "강남구", "max_rounds": "3", "model_id": "not-allowed"},
        )

    assert response.status_code == 422
    assert response.json()["detail"].startswith("model_id 'not-allowed' is not allowed")
