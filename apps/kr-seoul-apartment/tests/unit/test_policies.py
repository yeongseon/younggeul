from __future__ import annotations

# pyright: reportMissingImports=false

from datetime import date
from typing import Any

import pytest

from younggeul_app_kr_seoul_apartment.simulation.policies import (
    BrokerPolicy,
    BuyerPolicy,
    InvestorPolicy,
    LandlordPolicy,
    ParticipantPolicy,
    TenantPolicy,
    get_default_policy,
)
from younggeul_app_kr_seoul_apartment.simulation.schemas.round import DecisionContext, validate_v01_action
from younggeul_core.state.simulation import ActionProposal, ParticipantState, ScenarioSpec, SegmentState


def _build_segment(**overrides: Any) -> SegmentState:
    payload: dict[str, Any] = {
        "gu_code": "11680",
        "gu_name": "강남구",
        "current_median_price": 1_900_000_000,
        "current_volume": 200,
        "price_trend": "up",
        "sentiment_index": 0.7,
        "supply_pressure": -0.1,
    }
    payload.update(overrides)
    return SegmentState(**payload)


def _build_scenario(**overrides: Any) -> ScenarioSpec:
    payload: dict[str, Any] = {
        "scenario_name": "Policy Test",
        "target_gus": ["11680"],
        "target_period_start": date(2026, 1, 1),
        "target_period_end": date(2026, 12, 31),
        "shocks": [],
    }
    payload.update(overrides)
    return ScenarioSpec(**payload)


def _build_context(**overrides: Any) -> DecisionContext:
    payload: dict[str, Any] = {
        "round_no": 3,
        "segment": _build_segment(),
        "scenario": _build_scenario(),
    }
    payload.update(overrides)
    return DecisionContext(**payload)


def _build_participant(**overrides: Any) -> ParticipantState:
    payload: dict[str, Any] = {
        "participant_id": "p-001",
        "role": "buyer",
        "capital": 500_000_000,
        "holdings": 1,
        "sentiment": "neutral",
        "risk_tolerance": 0.8,
    }
    payload.update(overrides)
    return ParticipantState(**payload)


def _assert_valid_v01_action(action: ActionProposal) -> None:
    validate_v01_action(action)
    assert 0.0 <= action.confidence <= 1.0


class TestBuyerPolicy:
    def test_buys_on_bullish_non_downtrend_with_capital(self) -> None:
        policy = BuyerPolicy()
        participant = _build_participant(role="buyer", capital=700_000_000, risk_tolerance=0.75)
        context = _build_context(segment=_build_segment(price_trend="up", sentiment_index=0.8))

        action = policy.decide(participant, context)

        assert action.action_type == "buy"
        assert action.target_segment == "11680"
        assert action.proposed_value == {"max_budget": 700_000_000}
        assert action.confidence == pytest.approx(0.75 * 0.8)
        _assert_valid_v01_action(action)

    def test_holds_on_bearish_context(self) -> None:
        policy = BuyerPolicy()
        participant = _build_participant(role="buyer")
        context = _build_context(segment=_build_segment(sentiment_index=0.2, price_trend="down"))

        action = policy.decide(participant, context)

        assert action.action_type == "hold"
        assert action.proposed_value is None
        _assert_valid_v01_action(action)

    def test_holds_when_downtrend_even_with_positive_sentiment(self) -> None:
        policy = BuyerPolicy()
        participant = _build_participant(role="buyer", capital=300_000_000)
        context = _build_context(segment=_build_segment(sentiment_index=0.9, price_trend="down"))

        action = policy.decide(participant, context)

        assert action.action_type == "hold"

    def test_holds_with_zero_capital(self) -> None:
        policy = BuyerPolicy()
        participant = _build_participant(role="buyer", capital=0)
        context = _build_context(segment=_build_segment(sentiment_index=0.9, price_trend="up"))

        action = policy.decide(participant, context)

        assert action.action_type == "hold"
        assert action.confidence == 0.0

    def test_confidence_clamps_to_upper_bound(self) -> None:
        policy = BuyerPolicy()
        participant = _build_participant(role="buyer", risk_tolerance=1.0)
        context = _build_context(segment=_build_segment(sentiment_index=1.0, price_trend="flat"))

        action = policy.decide(participant, context)

        assert action.action_type == "buy"
        assert action.confidence == 1.0

    def test_deterministic_for_same_input(self) -> None:
        policy = BuyerPolicy()
        participant = _build_participant(role="buyer")
        context = _build_context(segment=_build_segment(sentiment_index=0.72, price_trend="up"))

        first = policy.decide(participant, context)
        second = policy.decide(participant, context)

        assert first == second


class TestInvestorPolicy:
    def test_buys_on_uptrend_and_high_sentiment(self) -> None:
        policy = InvestorPolicy()
        participant = _build_participant(role="investor", risk_tolerance=0.6, capital=800_000_000)
        context = _build_context(segment=_build_segment(price_trend="up", sentiment_index=0.9))

        action = policy.decide(participant, context)

        assert action.action_type == "buy"
        assert action.proposed_value == {"max_budget": 800_000_000}
        assert action.confidence == pytest.approx(0.6 * 0.9)
        _assert_valid_v01_action(action)

    def test_holds_when_sentiment_not_strictly_above_threshold(self) -> None:
        policy = InvestorPolicy()
        participant = _build_participant(role="investor")
        context = _build_context(segment=_build_segment(price_trend="up", sentiment_index=0.6))

        action = policy.decide(participant, context)

        assert action.action_type == "hold"

    def test_sells_on_downtrend_with_holdings(self) -> None:
        policy = InvestorPolicy()
        participant = _build_participant(role="investor", holdings=3, risk_tolerance=0.8)
        context = _build_context(segment=_build_segment(price_trend="down", sentiment_index=0.25))

        action = policy.decide(participant, context)

        assert action.action_type == "sell"
        assert action.proposed_value is None
        assert action.confidence == pytest.approx(0.8 * (1.0 - 0.25))
        _assert_valid_v01_action(action)

    def test_holds_on_downtrend_with_zero_holdings(self) -> None:
        policy = InvestorPolicy()
        participant = _build_participant(role="investor", holdings=0)
        context = _build_context(segment=_build_segment(price_trend="down", sentiment_index=0.1))

        action = policy.decide(participant, context)

        assert action.action_type == "hold"
        assert action.confidence == 0.0

    def test_holds_on_flat_trend(self) -> None:
        policy = InvestorPolicy()
        participant = _build_participant(role="investor")
        context = _build_context(segment=_build_segment(price_trend="flat", sentiment_index=0.9))

        action = policy.decide(participant, context)

        assert action.action_type == "hold"

    def test_deterministic_for_same_input(self) -> None:
        policy = InvestorPolicy()
        participant = _build_participant(role="investor", holdings=2)
        context = _build_context(segment=_build_segment(price_trend="down", sentiment_index=0.2))

        first = policy.decide(participant, context)
        second = policy.decide(participant, context)

        assert first == second


class TestTenantPolicy:
    @pytest.mark.parametrize(
        "context",
        [
            _build_context(segment=_build_segment(price_trend="up", sentiment_index=0.95)),
            _build_context(segment=_build_segment(price_trend="down", sentiment_index=0.05)),
            _build_context(segment=_build_segment(price_trend="flat", sentiment_index=0.5)),
        ],
    )
    def test_always_holds(self, context: DecisionContext) -> None:
        policy = TenantPolicy()
        participant = _build_participant(role="tenant", capital=0, holdings=0)

        action = policy.decide(participant, context)

        assert action.action_type == "hold"
        assert action.reasoning_summary == "Tenant holding — no buy/sell in v0.1"
        _assert_valid_v01_action(action)

    def test_deterministic_for_same_input(self) -> None:
        policy = TenantPolicy()
        participant = _build_participant(role="tenant", capital=0, holdings=0)
        context = _build_context(segment=_build_segment(sentiment_index=0.7))

        assert policy.decide(participant, context) == policy.decide(participant, context)


class TestLandlordPolicy:
    def test_sells_on_low_sentiment_with_holdings(self) -> None:
        policy = LandlordPolicy()
        participant = _build_participant(role="landlord", holdings=4, risk_tolerance=0.9)
        context = _build_context(segment=_build_segment(sentiment_index=0.2, price_trend="down"))

        action = policy.decide(participant, context)

        assert action.action_type == "sell"
        assert action.confidence == pytest.approx((1.0 - 0.2) * 0.9)
        _assert_valid_v01_action(action)

    def test_holds_when_low_sentiment_but_no_holdings(self) -> None:
        policy = LandlordPolicy()
        participant = _build_participant(role="landlord", holdings=0)
        context = _build_context(segment=_build_segment(sentiment_index=0.1, price_trend="down"))

        action = policy.decide(participant, context)

        assert action.action_type == "hold"

    def test_holds_on_threshold_boundary(self) -> None:
        policy = LandlordPolicy()
        participant = _build_participant(role="landlord", holdings=2)
        context = _build_context(segment=_build_segment(sentiment_index=0.3, price_trend="down"))

        action = policy.decide(participant, context)

        assert action.action_type == "hold"

    def test_holds_on_high_sentiment(self) -> None:
        policy = LandlordPolicy()
        participant = _build_participant(role="landlord", holdings=2)
        context = _build_context(segment=_build_segment(sentiment_index=0.8, price_trend="up"))

        action = policy.decide(participant, context)

        assert action.action_type == "hold"

    def test_confidence_never_exceeds_bounds(self) -> None:
        policy = LandlordPolicy()
        participant = _build_participant(role="landlord", holdings=3, risk_tolerance=1.0)
        context = _build_context(segment=_build_segment(sentiment_index=0.0, price_trend="down"))

        action = policy.decide(participant, context)

        assert action.action_type == "sell"
        assert action.confidence == 1.0

    def test_deterministic_for_same_input(self) -> None:
        policy = LandlordPolicy()
        participant = _build_participant(role="landlord", holdings=5)
        context = _build_context(segment=_build_segment(sentiment_index=0.2, price_trend="down"))

        assert policy.decide(participant, context) == policy.decide(participant, context)


class TestBrokerPolicy:
    @pytest.mark.parametrize(
        "context",
        [
            _build_context(segment=_build_segment(price_trend="up", sentiment_index=0.99)),
            _build_context(segment=_build_segment(price_trend="down", sentiment_index=0.01)),
            _build_context(segment=_build_segment(price_trend="flat", sentiment_index=0.5)),
        ],
    )
    def test_always_holds(self, context: DecisionContext) -> None:
        policy = BrokerPolicy()
        participant = _build_participant(role="broker", capital=0, holdings=0)

        action = policy.decide(participant, context)

        assert action.action_type == "hold"
        assert action.reasoning_summary == "Broker holding — facilitator role in v0.1"
        _assert_valid_v01_action(action)

    def test_deterministic_for_same_input(self) -> None:
        policy = BrokerPolicy()
        participant = _build_participant(role="broker", capital=0, holdings=0)
        context = _build_context(segment=_build_segment(sentiment_index=0.4, price_trend="flat"))

        assert policy.decide(participant, context) == policy.decide(participant, context)


class TestProtocolConformance:
    @pytest.mark.parametrize(
        "policy",
        [BuyerPolicy(), InvestorPolicy(), TenantPolicy(), LandlordPolicy(), BrokerPolicy()],
    )
    def test_all_heuristic_policies_satisfy_protocol(self, policy: ParticipantPolicy) -> None:
        assert isinstance(policy, ParticipantPolicy)


class TestRegistry:
    @pytest.mark.parametrize(
        ("role", "expected_type"),
        [
            ("buyer", BuyerPolicy),
            ("investor", InvestorPolicy),
            ("tenant", TenantPolicy),
            ("landlord", LandlordPolicy),
            ("broker", BrokerPolicy),
        ],
    )
    def test_get_default_policy_returns_expected_type(self, role: str, expected_type: type[ParticipantPolicy]) -> None:
        policy = get_default_policy(role)

        assert isinstance(policy, expected_type)
        assert isinstance(policy, ParticipantPolicy)

    def test_get_default_policy_raises_for_unknown_role(self) -> None:
        with pytest.raises(ValueError, match="No default policy for role: governor"):
            get_default_policy("governor")


class TestActionValidationAcrossContexts:
    @pytest.mark.parametrize(
        ("policy", "participant"),
        [
            (BuyerPolicy(), _build_participant(role="buyer")),
            (InvestorPolicy(), _build_participant(role="investor", holdings=2)),
            (TenantPolicy(), _build_participant(role="tenant", capital=0, holdings=0)),
            (LandlordPolicy(), _build_participant(role="landlord", holdings=2)),
            (BrokerPolicy(), _build_participant(role="broker", capital=0, holdings=0)),
        ],
    )
    @pytest.mark.parametrize(
        "context",
        [
            _build_context(segment=_build_segment(price_trend="up", sentiment_index=0.9)),
            _build_context(segment=_build_segment(price_trend="down", sentiment_index=0.1)),
            _build_context(segment=_build_segment(price_trend="flat", sentiment_index=0.5)),
        ],
    )
    def test_decisions_are_valid_v01_actions(
        self,
        policy: ParticipantPolicy,
        participant: ParticipantState,
        context: DecisionContext,
    ) -> None:
        action = policy.decide(participant, context)

        _assert_valid_v01_action(action)
        assert action.agent_id == participant.participant_id
        assert action.round_no == context.round_no
        assert action.target_segment == context.segment.gu_code
