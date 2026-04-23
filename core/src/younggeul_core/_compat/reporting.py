"""Opt-in delegation to abdp.reporting render helpers (see ADR-012 and the reporting render-flag work in issue #243, PR #251).

This module gives the CLI a stable seam for switching between the local
markdown rendering of `RenderedReport` (default, unchanged) and abdp's
deterministic JSON renderer (`abdp.reporting.render_json_report`),
selected at the call site by the `--render` flag on `simulate`.

Per the selective-adoption scope correction in ADR-012, the project does not adopt
abdp's `AuditLog` or evidence/claim contracts here; the reporting render-flag work only adopts the
output formatter, which operates on plain JSON-compatible primitives and
therefore needs no semantic alignment with the simulation provenance
model. Importing names from this module pulls in `abdp` lazily.
"""

from __future__ import annotations

from typing import Any

from younggeul_core._compat import require_abdp


def render_json_report(value: Any, *, indent: int = 2) -> str:
    """Render `value` to deterministic JSON via `abdp.reporting.render_json_report`.

    Accepts any JSON-compatible value (dict / list / primitives) and
    returns a string with sorted keys and stable separators. Suitable
    for feeding `RenderedReport.model_dump(mode="json")` directly.
    """
    require_abdp()
    from abdp.reporting import render_json_report as _abdp_render

    return str(_abdp_render(value, indent=indent))


__all__ = ["render_json_report"]
