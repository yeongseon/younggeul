from __future__ import annotations

from unittest.mock import MagicMock, patch

import click
import pytest

from younggeul_app_kr_seoul_apartment.connectors import client_factory

REQUIRED_PROVIDERS = client_factory.REQUIRED_PROVIDERS
build_client = client_factory.build_client


@pytest.fixture
def clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for provider in REQUIRED_PROVIDERS:
        token = provider.upper()
        monkeypatch.delenv(f"KPUBDATA_{token}_API_KEY", raising=False)
        monkeypatch.delenv(f"{token}_API_KEY", raising=False)


def _set_all_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    for provider in REQUIRED_PROVIDERS:
        monkeypatch.setenv(f"KPUBDATA_{provider.upper()}_API_KEY", f"key-{provider}")


def test_build_client_raises_clickexception_when_all_keys_missing(
    clear_env: None,
) -> None:
    with pytest.raises(click.ClickException) as exc_info:
        build_client()

    message = exc_info.value.message
    for provider in REQUIRED_PROVIDERS:
        assert f"KPUBDATA_{provider.upper()}_API_KEY" in message


def test_build_client_raises_clickexception_listing_only_missing_keys(
    clear_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KPUBDATA_BOK_API_KEY", "key-bok")

    with pytest.raises(click.ClickException) as exc_info:
        build_client()

    message = exc_info.value.message
    assert "KPUBDATA_DATAGO_API_KEY" in message
    assert "KPUBDATA_KOSIS_API_KEY" in message
    assert "KPUBDATA_BOK_API_KEY" not in message


def test_build_client_accepts_fallback_env_var(clear_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KPUBDATA_BOK_API_KEY", "key-bok")
    monkeypatch.setenv("KPUBDATA_KOSIS_API_KEY", "key-kosis")
    monkeypatch.setenv("DATAGO_API_KEY", "key-datago-fallback")

    sentinel = MagicMock(name="Client")
    with patch.object(client_factory.Client, "from_env", return_value=sentinel) as factory_mock:
        result = build_client()

    assert result is sentinel
    factory_mock.assert_called_once_with()


def test_build_client_returns_kpubdata_client_when_all_keys_present(
    clear_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_all_keys(monkeypatch)
    sentinel = MagicMock(name="Client")
    with patch.object(client_factory.Client, "from_env", return_value=sentinel) as factory_mock:
        result = build_client()

    assert result is sentinel
    factory_mock.assert_called_once_with()
