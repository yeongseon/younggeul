"""Simulation state schemas for scenarios, rounds, and report artifacts."""

from datetime import date, datetime
from typing import ClassVar, Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class RunMeta(BaseModel):
    """Store metadata describing a simulation run.

    Attributes:
        run_id: Unique run identifier.
        run_name: Human-readable run name.
        created_at: Timestamp when the run was created.
        model_id: Identifier of the model used for the run.
        config_hash: Optional hash of the run configuration.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    run_id: str
    run_name: str
    created_at: datetime
    model_id: str
    config_hash: str | None = None


class SnapshotRef(BaseModel):
    """Reference an input dataset snapshot used in a run.

    Attributes:
        dataset_snapshot_id: Snapshot identifier.
        created_at: Timestamp when the snapshot was created.
        table_count: Number of tables included in the snapshot.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    dataset_snapshot_id: str
    created_at: datetime
    table_count: int

    @field_validator("dataset_snapshot_id")
    @classmethod
    def validate_dataset_snapshot_id(cls, value: str) -> str:
        """Validate that dataset_snapshot_id is a 64-character hex string.

        Args:
            value: The value to validate.

        Returns:
            The validated value.

        Raises:
            ValueError: If validation fails.
        """

        if len(value) != 64:
            raise ValueError("dataset_snapshot_id must be exactly 64 hex characters")
        if any(character not in "0123456789abcdefABCDEF" for character in value):
            raise ValueError("dataset_snapshot_id must be hex")
        return value


class Shock(BaseModel):
    """Describe an exogenous shock applied to a simulation scenario.

    Attributes:
        shock_type: Shock category applied in the simulation.
        description: Human-readable description of the shock.
        magnitude: Signed intensity of the shock.
        target_segments: Segment identifiers targeted by the shock.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    shock_type: Literal["interest_rate", "regulation", "supply", "demand", "external"]
    description: str
    magnitude: float
    target_segments: list[str] = Field(default_factory=list)

    @field_validator("magnitude")
    @classmethod
    def validate_magnitude(cls, value: float) -> float:
        """Validate that magnitude is between -1.0 and 1.0.

        Args:
            value: The value to validate.

        Returns:
            The validated value.

        Raises:
            ValueError: If validation fails.
        """

        if not -1.0 <= value <= 1.0:
            raise ValueError("magnitude must be between -1.0 and 1.0")
        return value


class ScenarioSpec(BaseModel):
    """Define scenario boundaries and shocks for a simulation run.

    Attributes:
        scenario_name: Name of the scenario.
        target_gus: District codes targeted by the scenario.
        target_period_start: Scenario start date.
        target_period_end: Scenario end date.
        shocks: Shocks to apply during the scenario.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    scenario_name: str
    target_gus: list[str]
    target_period_start: date
    target_period_end: date
    shocks: list[Shock] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_target_period(self) -> "ScenarioSpec":
        """Validate that the scenario end date is not earlier than the start date.

        Returns:
            The validated instance.

        Raises:
            ValueError: If validation fails.
        """

        if self.target_period_end < self.target_period_start:
            raise ValueError("target_period_end must be greater than or equal to target_period_start")
        return self


class SegmentState(BaseModel):
    """Capture market state metrics for a district segment.

    Attributes:
        gu_code: District code.
        gu_name: District name.
        current_median_price: Current median price.
        current_volume: Current transaction volume.
        price_trend: Current directional price trend.
        sentiment_index: Sentiment score for the segment.
        supply_pressure: Supply pressure indicator.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    gu_code: str
    gu_name: str
    current_median_price: int
    current_volume: int
    price_trend: Literal["up", "down", "flat"]
    sentiment_index: float
    supply_pressure: float

    @field_validator("sentiment_index")
    @classmethod
    def validate_sentiment_index(cls, value: float) -> float:
        """Validate that sentiment_index is between 0.0 and 1.0.

        Args:
            value: The value to validate.

        Returns:
            The validated value.

        Raises:
            ValueError: If validation fails.
        """

        if not 0.0 <= value <= 1.0:
            raise ValueError("sentiment_index must be between 0.0 and 1.0")
        return value

    @field_validator("supply_pressure")
    @classmethod
    def validate_supply_pressure(cls, value: float) -> float:
        """Validate that supply_pressure is between -1.0 and 1.0.

        Args:
            value: The value to validate.

        Returns:
            The validated value.

        Raises:
            ValueError: If validation fails.
        """

        if not -1.0 <= value <= 1.0:
            raise ValueError("supply_pressure must be between -1.0 and 1.0")
        return value


class ParticipantState(BaseModel):
    """Represent simulation participant positions and preferences.

    Attributes:
        participant_id: Unique participant identifier.
        role: Role assigned to the participant.
        capital: Available capital.
        holdings: Number of held units or positions.
        sentiment: Participant sentiment state.
        risk_tolerance: Participant risk tolerance score.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    participant_id: str
    role: Literal["buyer", "investor", "tenant", "landlord", "broker"]
    capital: int
    holdings: int
    sentiment: Literal["bullish", "bearish", "neutral"]
    risk_tolerance: float

    @field_validator("risk_tolerance")
    @classmethod
    def validate_risk_tolerance(cls, value: float) -> float:
        """Validate that risk_tolerance is between 0.0 and 1.0.

        Args:
            value: The value to validate.

        Returns:
            The validated value.

        Raises:
            ValueError: If validation fails.
        """

        if not 0.0 <= value <= 1.0:
            raise ValueError("risk_tolerance must be between 0.0 and 1.0")
        return value


class ActionProposal(BaseModel):
    """Represent a participant or governance action proposed for a round.

    Attributes:
        agent_id: Identifier of the proposing agent.
        round_no: Target round number.
        action_type: Action category proposed by the agent.
        target_segment: Segment targeted by the action.
        confidence: Confidence score for the proposal.
        reasoning_summary: Short explanation for the proposed action.
        proposed_value: Optional structured payload with action details.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    agent_id: str
    round_no: int
    action_type: Literal["buy", "sell", "hold", "rent_out", "regulate", "adjust_rate"]
    target_segment: str
    confidence: float
    reasoning_summary: str
    proposed_value: dict[str, object] | None = None

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, value: float) -> float:
        """Validate that confidence is between 0.0 and 1.0.

        Args:
            value: The value to validate.

        Returns:
            The validated value.

        Raises:
            ValueError: If validation fails.
        """

        if not 0.0 <= value <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
        return value


class RoundOutcome(BaseModel):
    """Summarize resolved outcomes for a completed simulation round.

    Attributes:
        round_no: Round number.
        cleared_volume: Cleared transaction volume by segment.
        price_changes: Price changes by segment.
        governance_applied: Governance actions applied during resolution.
        market_actions_resolved: Count of resolved market actions.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    round_no: int
    cleared_volume: dict[str, int]
    price_changes: dict[str, float]
    governance_applied: list[str]
    market_actions_resolved: int


class ReportClaim(BaseModel):
    """Represent a generated report claim tied to evidence and gating.

    Attributes:
        claim_id: Unique claim identifier.
        claim_json: Structured claim payload.
        evidence_ids: Evidence identifiers supporting the claim.
        gate_status: Current gate status for the claim.
        repair_count: Number of applied repair attempts.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    claim_id: str
    claim_json: dict[str, object]
    evidence_ids: list[str]
    gate_status: Literal["pending", "passed", "failed", "repaired"] = "pending"
    repair_count: int = 0

    @field_validator("repair_count")
    @classmethod
    def validate_repair_count(cls, value: int) -> int:
        """Validate that repair_count does not exceed the retry limit.

        Args:
            value: The value to validate.

        Returns:
            The validated value.

        Raises:
            ValueError: If validation fails.
        """

        if value > 2:
            raise ValueError("repair_count must be less than or equal to 2")
        return value


class SimulationState(TypedDict):
    """Define the mutable state container used across simulation rounds.

    Attributes:
        run_meta: Metadata for the current run.
        snapshot: Input dataset snapshot reference.
        scenario: Active scenario definition.
        round_no: Current round number.
        max_rounds: Maximum number of rounds.
        world: Segment state indexed by segment identifier.
        participants: Participant state indexed by participant identifier.
        governance_actions: Governance proposals indexed by action key.
        market_actions: Market proposals indexed by action key.
        last_outcome: Most recent round outcome if available.
        event_refs: Event reference identifiers.
        evidence_refs: Evidence reference identifiers.
        report_claims: Report claims generated so far.
        warnings: Collected warning messages.
    """

    run_meta: RunMeta
    snapshot: SnapshotRef
    scenario: ScenarioSpec
    round_no: int
    max_rounds: int
    world: dict[str, SegmentState]
    participants: dict[str, ParticipantState]
    governance_actions: dict[str, ActionProposal]
    market_actions: dict[str, ActionProposal]
    last_outcome: RoundOutcome | None
    event_refs: list[str]
    evidence_refs: list[str]
    report_claims: list[ReportClaim]
    warnings: list[str]
