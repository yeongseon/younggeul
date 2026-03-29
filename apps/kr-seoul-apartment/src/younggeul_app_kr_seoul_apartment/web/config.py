from __future__ import annotations

import os


def get_allowed_models() -> tuple[str, ...]:
    raw = os.getenv("YOUNGGEUL_ALLOWED_MODELS", "stub,gpt-4o-mini")
    models = tuple(model.strip() for model in raw.split(",") if model.strip())
    return models or ("stub",)


def validate_model_id(model_id: str) -> None:
    allowed_models = get_allowed_models()
    if model_id not in allowed_models:
        raise ValueError(f"model_id '{model_id}' is not allowed")


def validate_max_rounds(max_rounds: int) -> None:
    if max_rounds < 1 or max_rounds > 10:
        raise ValueError("max_rounds must be between 1 and 10")
