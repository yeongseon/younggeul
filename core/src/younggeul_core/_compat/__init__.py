"""Backend selection compatibility layer for younggeul_core.

See ADR-012 (docs/adr/012-abdp-backed-core.md). Subsequent milestones
(M3-M5) will route subsystem imports through this module so the backend
can be flipped via the ``YOUNGGEUL_CORE_BACKEND`` environment variable
without touching call sites.

Public surface intentionally minimal in M2: just the flag-reader and a
single ``require_abdp()`` helper that produces a clear error if the
``abdp`` extra is requested but not installed.
"""

from __future__ import annotations

import os
from typing import Final, Literal

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
    return raw  # type: ignore[return-value]


def require_abdp() -> None:
    """Import ``abdp`` or raise a friendly error pointing to the extra."""
    try:
        import abdp  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            "The 'abdp' backend was requested "
            f"({ENV_VAR}=abdp) but the abdp package is not installed. "
            "Install it via:  pip install -e '.[abdp]'  "
            "(see ADR-012 for details)."
        ) from exc


__all__ = ["Backend", "DEFAULT_BACKEND", "ENV_VAR", "get_backend", "require_abdp"]
