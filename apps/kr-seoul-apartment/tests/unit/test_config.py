from __future__ import annotations

from importlib import import_module

import pytest

config_module = import_module("younggeul_app_kr_seoul_apartment.web.config")

get_allowed_models = config_module.get_allowed_models
validate_model_id = config_module.validate_model_id


def test_get_allowed_models_includes_github_models_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("YOUNGGEUL_ALLOWED_MODELS", raising=False)

    allowed_models = get_allowed_models()

    assert allowed_models == ("stub", "gpt-4o-mini", "github/openai/gpt-4o-mini")


def test_validate_model_id_accepts_github_models_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("YOUNGGEUL_ALLOWED_MODELS", raising=False)

    validate_model_id("github/openai/gpt-4o-mini")


def test_validate_model_id_rejects_unknown_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("YOUNGGEUL_ALLOWED_MODELS", raising=False)

    with pytest.raises(ValueError, match="model_id 'unknown-model' is not allowed"):
        validate_model_id("unknown-model")
