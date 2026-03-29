from __future__ import annotations

from importlib import import_module

from fastapi.testclient import TestClient

web_app = import_module("younggeul_app_kr_seoul_apartment.web.app")


def test_health_endpoint_returns_expected_payload() -> None:
    app = web_app.create_app()
    with TestClient(app) as client:
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok", "version": "0.2.0"}
