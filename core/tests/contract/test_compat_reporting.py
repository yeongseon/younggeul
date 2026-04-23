from __future__ import annotations

import importlib
import json

import pytest

pytest.importorskip("abdp")


def test_compat_reporting_delegates_to_abdp() -> None:
    """`_compat.reporting.render_json_report` must thin-wrap the abdp helper
    (no logic of its own beyond `require_abdp()` and a `str(...)` cast)."""
    mod = importlib.import_module("younggeul_core._compat.reporting")
    from abdp.reporting import render_json_report as abdp_render

    payload = {"b": 1, "a": [3, 2, 1]}
    assert mod.render_json_report(payload) == abdp_render(payload)


def test_compat_reporting_accepts_plain_dict() -> None:
    """The renderer accepts JSON-compatible primitives directly so that
    callers can feed `RenderedReport.model_dump(mode='json')` without
    any intermediate adapter."""
    mod = importlib.import_module("younggeul_core._compat.reporting")
    rendered = mod.render_json_report({"run_id": "abc", "round_no": 2})
    parsed = json.loads(rendered)
    assert parsed == {"run_id": "abc", "round_no": 2}


def test_compat_reporting_output_is_deterministic_sorted() -> None:
    """abdp's renderer sorts keys; verify two equivalent dicts produce
    byte-identical output regardless of insertion order."""
    mod = importlib.import_module("younggeul_core._compat.reporting")
    a = mod.render_json_report({"a": 1, "b": 2})
    b = mod.render_json_report({"b": 2, "a": 1})
    assert a == b
    assert a.index('"a"') < a.index('"b"')
