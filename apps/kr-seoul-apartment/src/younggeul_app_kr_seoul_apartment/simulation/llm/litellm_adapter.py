from __future__ import annotations

import json
from importlib import import_module
from typing import Any, Sequence, TypeVar

from pydantic import BaseModel, ValidationError

from .ports import LLMMessage

T = TypeVar("T", bound=BaseModel)


class StructuredLLMTransportError(RuntimeError):
    pass


class StructuredLLMResponseError(ValueError):
    pass


class LiteLLMStructuredLLM:
    def __init__(self, model: str, **default_kwargs: Any) -> None:
        self.model = model
        self._default_kwargs = default_kwargs

    def generate_structured(
        self,
        *,
        messages: Sequence[LLMMessage],
        response_model: type[T],
        temperature: float = 0.0,
    ) -> T:
        litellm = import_module("litellm")

        schema = response_model.model_json_schema()
        response_format = {
            "type": "json_schema",
            "json_schema": {"name": response_model.__name__, "schema": schema},
        }

        try:
            response = litellm.completion(
                model=self.model,
                messages=list(messages),
                temperature=temperature,
                response_format=response_format,
                **self._default_kwargs,
            )
        except Exception as exc:
            raise StructuredLLMTransportError(f"LLM call failed: {exc}") from exc

        raw_content = response.choices[0].message.content
        if raw_content is None:
            raise StructuredLLMResponseError("LLM returned empty content")

        try:
            data = json.loads(raw_content)
        except json.JSONDecodeError as exc:
            raise StructuredLLMResponseError(f"LLM returned invalid JSON: {raw_content[:200]}") from exc

        try:
            return response_model.model_validate(data)
        except ValidationError as exc:
            raise StructuredLLMResponseError(f"LLM output failed schema validation: {exc}") from exc
