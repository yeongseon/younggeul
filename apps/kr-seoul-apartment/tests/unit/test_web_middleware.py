from __future__ import annotations

from importlib import import_module
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from younggeul_app_kr_seoul_apartment.web.run_store import RunStore

web_app = import_module("younggeul_app_kr_seoul_apartment.web.app")
middleware_module = import_module("younggeul_app_kr_seoul_apartment.web.middleware")


def test_metrics_middleware_records_request_metrics_with_normalized_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request_counter = MagicMock()
    duration_histogram = MagicMock()

    monkeypatch.setattr(middleware_module, "web_requests_total", lambda: request_counter)
    monkeypatch.setattr(middleware_module, "web_request_duration_seconds", lambda: duration_histogram)
    monkeypatch.setattr(web_app, "RunStore", lambda base_dir=None: RunStore(base_dir=tmp_path / "runs"))

    app = web_app.create_app()
    with TestClient(app) as client:
        response = client.get("/simulate/123e4567-e89b-12d3-a456-426614174000")

    assert response.status_code == 404
    request_counter.add.assert_called_once_with(
        1,
        attributes={
            "app": "kr-seoul-apartment",
            "method": "GET",
            "path": "/simulate/:id",
            "status_code": "404",
        },
    )

    duration_histogram.record.assert_called_once()
    _, duration_kwargs = duration_histogram.record.call_args
    assert duration_kwargs["attributes"] == {
        "app": "kr-seoul-apartment",
        "method": "GET",
        "path": "/simulate/:id",
    }
