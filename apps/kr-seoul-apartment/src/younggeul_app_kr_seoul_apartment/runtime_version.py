from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

_PACKAGE_NAME = "younggeul"


def get_runtime_version() -> str:
    try:
        return version(_PACKAGE_NAME)
    except PackageNotFoundError:
        return "dev"
