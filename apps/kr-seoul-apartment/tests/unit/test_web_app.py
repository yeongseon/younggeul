from __future__ import annotations

import asyncio
from importlib import import_module

web_app = import_module("younggeul_app_kr_seoul_apartment.web.app")
health_routes = import_module("younggeul_app_kr_seoul_apartment.web.routes.health")


def test_health_endpoint_returns_expected_payload() -> None:
    payload = asyncio.run(health_routes.health())

    assert payload["status"] == "ok"
    assert payload["version"] == web_app.get_runtime_version()


def test_placeholder_api_routes_are_not_exposed() -> None:
    app = web_app.create_app()
    paths = {route.path for route in app.routes}

    assert "/health" in paths
    assert "/simulate" in paths
    assert "/ui/" in paths
    assert "/snapshot" not in paths
    assert "/baseline" not in paths
