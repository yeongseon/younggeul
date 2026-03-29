from __future__ import annotations

# pyright: reportMissingImports=false

from datetime import date
from typing import Any, Callable

import pytest
from pydantic import BaseModel, ValidationError

from younggeul_app_kr_seoul_apartment.simulation.schemas.round import (
    DecisionContext,
    ParticipantDelta,
    RoundResolvedPayload,
    SegmentDelta,
    V01_ACTION_TYPES,
    validate_v01_action,
)
from younggeul_core.state.simulation import ActionProposal, RoundOutcome, ScenarioSpec, SegmentState, Shock


def _build_segment_state(**overrides: Any) -> SegmentState:
    payload: dict[str, Any] = {
        "gu_code": "11680",
        "gu_name": "강남구",
        "current_median_price": 1_800_000_000,
        "current_volume": 240,
        "price_trend": "up",
        "sentiment_index": 0.7,
        "supply_pressure": -0.2,
    }
    payload.update(overrides)
    return SegmentState(**payload)


def _build_shock(**overrides: Any) -> Shock:
    payload: dict[str, Any] = {
        "shock_type": "interest_rate",
        "description": "Rate increased",
        "magnitude": 0.2,
        "target_segments": ["11680"],
    }
    payload.update(overrides)
    return Shock(**payload)


def _build_scenario(**overrides: Any) -> ScenarioSpec:
    payload: dict[str, Any] = {
        "scenario_name": "Stress Case",
        "target_gus": ["11680", "11650"],
        "target_period_start": date(2026, 1, 1),
        "target_period_end": date(2026, 6, 1),
        "shocks": [_build_shock()],
    }
    payload.update(overrides)
    return ScenarioSpec(**payload)


def _build_round_outcome(**overrides: Any) -> RoundOutcome:
    payload: dict[str, Any] = {
        "round_no": 1,
        "cleared_volume": {"11680": 15},
        "price_changes": {"11680": 0.01},
        "governance_applied": ["ltv_tighten"],
        "market_actions_resolved": 11,
    }
    payload.update(overrides)
    return RoundOutcome(**payload)


def _build_action_proposal(**overrides: Any) -> ActionProposal:
    payload: dict[str, Any] = {
        "agent_id": "buyer-001",
        "round_no": 2,
        "action_type": "buy",
        "target_segment": "11680",
        "confidence": 0.8,
        "reasoning_summary": "Demand remains resilient.",
        "proposed_value": {"units": 1},
    }
    payload.update(overrides)
    return ActionProposal(**payload)


def _build_decision_context(**overrides: Any) -> DecisionContext:
    payload: dict[str, Any] = {
        "round_no": 2,
        "segment": _build_segment_state(),
        "scenario": _build_scenario(),
        "last_outcome": _build_round_outcome(),
        "active_shocks": [_build_shock()],
        "governance_modifiers": {"ltv_cap": 0.7},
    }
    payload.update(overrides)
    return DecisionContext(**payload)


def _build_segment_delta(**overrides: Any) -> SegmentDelta:
    payload: dict[str, Any] = {
        "gu_code": "11680",
        "price_change_pct": 0.01,
        "volume_change": 8,
        "new_median_price": 1_820_000_000,
        "new_volume": 248,
    }
    payload.update(overrides)
    return SegmentDelta(**payload)


def _build_participant_delta(**overrides: Any) -> ParticipantDelta:
    payload: dict[str, Any] = {
        "participant_id": "buyer-001",
        "capital_change": -20_000_000,
        "holdings_change": 1,
        "new_capital": 880_000_000,
        "new_holdings": 2,
    }
    payload.update(overrides)
    return ParticipantDelta(**payload)


def _build_round_payload(**overrides: Any) -> RoundResolvedPayload:
    payload: dict[str, Any] = {
        "round_no": 2,
        "segment_deltas": {
            "11680": _build_segment_delta(),
            "11650": _build_segment_delta(gu_code="11650", price_change_pct=-0.005),
        },
        "participant_deltas": {
            "buyer-001": _build_participant_delta(),
            "investor-007": _build_participant_delta(participant_id="investor-007", holdings_change=-1, new_holdings=0),
        },
        "transactions_count": 31,
        "summary": "Round resolved with mild divergence between segments.",
    }
    payload.update(overrides)
    return RoundResolvedPayload(**payload)


class TestDecisionContext:
    def test_constructs_with_valid_data(self) -> None:
        context = _build_decision_context()

        assert context.round_no == 2
        assert context.segment.gu_code == "11680"
        assert context.last_outcome is not None

    def test_last_outcome_defaults_to_none(self) -> None:
        context = _build_decision_context(last_outcome=None)

        assert context.last_outcome is None

    def test_allows_empty_active_shocks_and_governance_modifiers(self) -> None:
        context = _build_decision_context(active_shocks=[], governance_modifiers={})

        assert context.active_shocks == []
        assert context.governance_modifiers == {}

    def test_rejects_negative_round_no(self) -> None:
        with pytest.raises(ValidationError):
            _build_decision_context(round_no=-1)

    def test_is_frozen(self) -> None:
        context = _build_decision_context()

        with pytest.raises(ValidationError):
            setattr(context, "round_no", 3)


class TestSegmentDelta:
    @pytest.mark.parametrize("value", [-0.05, 0.0, 0.05])
    def test_accepts_price_change_pct_boundaries(self, value: float) -> None:
        model = _build_segment_delta(price_change_pct=value)

        assert model.price_change_pct == value

    @pytest.mark.parametrize("value", [-0.051, 0.051])
    def test_rejects_out_of_bounds_price_change_pct(self, value: float) -> None:
        with pytest.raises(ValidationError):
            _build_segment_delta(price_change_pct=value)

    def test_rejects_negative_new_median_price(self) -> None:
        with pytest.raises(ValidationError):
            _build_segment_delta(new_median_price=-1)

    def test_rejects_negative_new_volume(self) -> None:
        with pytest.raises(ValidationError):
            _build_segment_delta(new_volume=-1)

    def test_is_frozen(self) -> None:
        model = _build_segment_delta()

        with pytest.raises(ValidationError):
            setattr(model, "new_volume", 1)


class TestParticipantDelta:
    def test_constructs_and_serializes(self) -> None:
        model = _build_participant_delta()
        dumped = model.model_dump()

        assert dumped["participant_id"] == "buyer-001"
        assert dumped["new_holdings"] == 2

    def test_allows_zero_values(self) -> None:
        model = _build_participant_delta(
            capital_change=0,
            holdings_change=0,
            new_capital=0,
            new_holdings=0,
        )

        assert model.new_capital == 0
        assert model.new_holdings == 0

    def test_rejects_negative_new_holdings(self) -> None:
        with pytest.raises(ValidationError):
            _build_participant_delta(new_holdings=-1)

    def test_is_frozen(self) -> None:
        model = _build_participant_delta()

        with pytest.raises(ValidationError):
            setattr(model, "new_capital", 1)


class TestRoundResolvedPayload:
    def test_constructs_with_multiple_deltas(self) -> None:
        payload = _build_round_payload()

        assert payload.round_no == 2
        assert set(payload.segment_deltas.keys()) == {"11680", "11650"}
        assert set(payload.participant_deltas.keys()) == {"buyer-001", "investor-007"}
        assert payload.transactions_count == 31

    def test_rejects_negative_round_no(self) -> None:
        with pytest.raises(ValidationError):
            _build_round_payload(round_no=-1)

    def test_rejects_negative_transactions_count(self) -> None:
        with pytest.raises(ValidationError):
            _build_round_payload(transactions_count=-1)

    def test_is_frozen(self) -> None:
        payload = _build_round_payload()

        with pytest.raises(ValidationError):
            setattr(payload, "summary", "changed")


class TestRoundTripSerialization:
    @pytest.mark.parametrize(
        "builder",
        [
            _build_decision_context,
            _build_segment_delta,
            _build_participant_delta,
            _build_round_payload,
        ],
    )
    def test_model_dump_and_validate_round_trip(self, builder: Callable[[], BaseModel]) -> None:
        model = builder()
        restored = type(model).model_validate(model.model_dump())

        assert restored == model


class TestV01ActionValidation:
    def test_action_type_constant(self) -> None:
        assert V01_ACTION_TYPES == frozenset({"buy", "sell", "hold"})

    @pytest.mark.parametrize("action_type", ["buy", "sell", "hold"])
    def test_validate_v01_action_accepts_supported_types(self, action_type: str) -> None:
        action = _build_action_proposal(action_type=action_type)

        validate_v01_action(action)

    @pytest.mark.parametrize("action_type", ["regulate", "adjust_rate", "rent_out"])
    def test_validate_v01_action_rejects_unsupported_types(self, action_type: str) -> None:
        action = _build_action_proposal(action_type=action_type)

        with pytest.raises(ValueError, match="Unsupported v0.1 action_type"):
            validate_v01_action(action)
