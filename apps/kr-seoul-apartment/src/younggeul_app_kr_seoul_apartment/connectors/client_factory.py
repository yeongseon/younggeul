"""Factory for the kpubdata Client used by the live ingest pipeline.

Single source of truth for constructing an authenticated kpubdata client and
surfacing actionable error messages when API keys are absent.
"""

from __future__ import annotations

import os

import click
from kpubdata import Client

REQUIRED_PROVIDERS: tuple[str, ...] = ("datago", "bok", "kosis")


def _env_var_names(provider: str) -> tuple[str, str]:
    token = provider.upper()
    return (f"KPUBDATA_{token}_API_KEY", f"{token}_API_KEY")


def _missing_providers() -> list[str]:
    missing: list[str] = []
    for provider in REQUIRED_PROVIDERS:
        primary, fallback = _env_var_names(provider)
        if not os.environ.get(primary) and not os.environ.get(fallback):
            missing.append(provider)
    return missing


def build_client() -> Client:
    """Construct a ``kpubdata.Client`` from environment variables.

    Validates that all three provider API keys are present in the environment
    before constructing the client so the caller gets one clear error message
    instead of a deferred ``ConfigError`` at first request.

    Raises:
        click.ClickException: If any required ``KPUBDATA_*_API_KEY`` env var
            (or its non-prefixed fallback) is missing.

    Returns:
        A configured kpubdata ``Client`` ready for live API calls.
    """
    missing = _missing_providers()
    if missing:
        expected = ", ".join(_env_var_names(provider)[0] for provider in missing)
        message = (
            f"Missing kpubdata API key(s) for: {', '.join(missing)}."
            + f" Set the following environment variable(s): {expected}."
        )
        raise click.ClickException(message)
    return Client.from_env()


__all__ = ["REQUIRED_PROVIDERS", "build_client"]
