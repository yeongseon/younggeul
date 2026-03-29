from __future__ import annotations

# pyright: reportMissingImports=false

from pydantic import BaseModel, Field, field_validator

from younggeul_core.state.simulation import ActionProposal, RoundOutcome, ScenarioSpec, SegmentState, Shock

V01_ACTION_TYPES: frozenset[str] = frozenset({"buy", "sell", "hold"})


class DecisionContext(BaseModel, frozen=True):
    round_no: int = Field(ge=0)
    segment: SegmentState
    scenario: ScenarioSpec
    last_outcome: RoundOutcome | None = None
    active_shocks: list[Shock] = Field(default_factory=list)
    governance_modifiers: dict[str, float] = Field(default_factory=dict)


class SegmentDelta(BaseModel, frozen=True):
    gu_code: str
    price_change_pct: float
    volume_change: int
    new_median_price: int = Field(ge=0)
    new_volume: int = Field(ge=0)

    @field_validator("price_change_pct")
    @classmethod
    def validate_price_change_pct(cls, value: float) -> float:
        if not -0.05 <= value <= 0.05:
            raise ValueError("price_change_pct must be between -0.05 and 0.05")
        return value


class ParticipantDelta(BaseModel, frozen=True):
    participant_id: str
    capital_change: int
    holdings_change: int
    new_capital: int
    new_holdings: int = Field(ge=0)


class RoundResolvedPayload(BaseModel, frozen=True):
    round_no: int = Field(ge=0)
    segment_deltas: dict[str, SegmentDelta]
    participant_deltas: dict[str, ParticipantDelta]
    transactions_count: int = Field(ge=0)
    summary: str


def validate_v01_action(action: ActionProposal) -> None:
    if action.action_type not in V01_ACTION_TYPES:
        raise ValueError(f"Unsupported v0.1 action_type: {action.action_type}")
