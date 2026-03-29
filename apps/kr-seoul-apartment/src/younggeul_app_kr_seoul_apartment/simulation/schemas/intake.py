from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class IntakePlan(BaseModel, frozen=True):
    user_query: str
    objective: str
    analysis_mode: Literal["baseline", "stress", "compare"]
    geography_hint: str | None = None
    segment_hint: str | None = None
    horizon_months: int = Field(ge=1, le=120)
    requested_shocks: list[str] = Field(default_factory=list)
    participant_focus: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)
