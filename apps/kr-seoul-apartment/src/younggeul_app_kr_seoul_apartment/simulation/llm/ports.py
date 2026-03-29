from __future__ import annotations

from typing import Literal, Protocol, Sequence, TypeVar

from pydantic import BaseModel
from typing_extensions import TypedDict

T = TypeVar("T", bound=BaseModel)


class LLMMessage(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str


class StructuredLLM(Protocol):
    def generate_structured(
        self,
        *,
        messages: Sequence[LLMMessage],
        response_model: type[T],
        temperature: float = 0.0,
    ) -> T: ...
