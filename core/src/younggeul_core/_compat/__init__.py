"""Backend selection compatibility layer for younggeul_core.

See ADR-012 (docs/adr/012-abdp-backed-core.md) and the final selective-adoption
inventory recorded there. The shipped adopted
surfaces are routed through sibling modules in this package
(:mod:`younggeul_core._compat.data`,
:mod:`younggeul_core._compat.reporting`,
:mod:`younggeul_core._compat.ids`,
:mod:`younggeul_core._compat.scenario`) plus
:mod:`younggeul_core.connectors.hashing`. They consult
:func:`get_backend` at call time so the same call sites work under
both backends without import-time wiring.

The default backend remains ``"local"`` indefinitely per the 2026-04-23
finalization ruling (no default flip): younggeul-owned domain types
(:mod:`younggeul_core.state.simulation`, :mod:`younggeul_core.storage`)
and the LangGraph runtime stay local; abdp is adopted selectively
where semantics already match.
"""

from __future__ import annotations

import os
from typing import Final, Literal, cast

Backend = Literal["local", "abdp"]

ENV_VAR: Final[str] = "YOUNGGEUL_CORE_BACKEND"
DEFAULT_BACKEND: Final[Backend] = "local"
_VALID_BACKENDS: Final[frozenset[str]] = frozenset({"local", "abdp"})


def get_backend() -> Backend:
    """Return the currently configured younggeul_core backend.

    Reads ``YOUNGGEUL_CORE_BACKEND`` at call time (not import time) so tests
    can switch backends via ``monkeypatch.setenv``. Defaults to ``"local"``
    so existing installs keep their v0.3.0 behavior.

    Raises:
        ValueError: if the env var is set to an unsupported value.
    """
    raw = os.environ.get(ENV_VAR, DEFAULT_BACKEND).strip().lower()
    if raw not in _VALID_BACKENDS:
        raise ValueError(f"{ENV_VAR}={raw!r} is not supported. Valid values: {sorted(_VALID_BACKENDS)}.")
    return cast(Backend, raw)


def require_abdp() -> None:
    """Import ``abdp`` or raise a friendly error pointing to the extra."""
    try:
        import abdp as _abdp

        _ = _abdp
    except ImportError as exc:
        raise ImportError(
            f"The 'abdp' backend was requested ({ENV_VAR}=abdp) but the abdp package is not installed. "
            "Install it via:  pip install -e '.[abdp]'  (see ADR-012 for details)."
        ) from exc


__all__ = ["Backend", "DEFAULT_BACKEND", "ENV_VAR", "get_backend", "require_abdp"]
