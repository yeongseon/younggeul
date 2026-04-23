"""Pure round-resolution math extracted from :mod:`round_resolver`.

Per Oracle's M9' design ruling F (REAL SHADOW EXECUTION, not synthesis):
the abdp ScenarioRunner adapter must invoke the *same* resolution logic
the LangGraph node uses, never a fork. This module owns that single,
pure implementation; the LangGraph node delegates to it and adds event
publication on top, while the M9'-c shadow runner wraps it in a
:class:`younggeul_core._compat.scenario.CallableResolver`.

The function is deliberately free of LangGraph state, event stores, and
side effects so both call sites can use it deterministically.
"""

from __future__ import annotations

# pyright: reportMissingImports=false

from typing import Any, Literal, NamedTuple

from younggeul_core.state.simulation import ParticipantState, RoundOutcome, SegmentState

from ..schemas.round import ParticipantDelta, RoundResolvedPayload, SegmentDelta, validate_v01_action


class ResolveRoundResult(NamedTuple):
    """Outputs of one pure round resolution."""

    new_world: dict[str, SegmentState]
    new_participants: dict[str, ParticipantState]
    outcome: RoundOutcome
    payload: RoundResolvedPayload
    warnings: list[str]


def _clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def _copy_participant(participant: ParticipantState, *, capital: int, holdings: int) -> ParticipantState:
    return ParticipantState(
        participant_id=participant.participant_id,
        role=participant.role,
        capital=capital,
        holdings=holdings,
        sentiment=participant.sentiment,
        risk_tolerance=participant.risk_tolerance,
    )


def _copy_segment(
    segment: SegmentState,
    *,
    median_price: int,
    volume: int,
    trend: Literal["up", "down", "flat"],
    sentiment_index: float,
) -> SegmentState:
    return SegmentState(
        gu_code=segment.gu_code,
        gu_name=segment.gu_name,
        current_median_price=median_price,
        current_volume=volume,
        price_trend=trend,
        sentiment_index=sentiment_index,
        supply_pressure=segment.supply_pressure,
    )


def pure_resolve_round(
    *,
    world: dict[str, SegmentState],
    participants: dict[str, ParticipantState],
    market_actions: dict[str, Any],
    round_no: int,
) -> ResolveRoundResult:
    """Apply one round's market actions to ``world`` and ``participants``.

    Pure: never mutates inputs, never raises for empty inputs, never
    performs I/O. Mirrors the round resolver semantics 1:1.
    """
    warnings: list[str] = []

    if not participants:
        outcome = RoundOutcome(
            round_no=round_no,
            cleared_volume={},
            price_changes={},
            governance_applied=[],
            market_actions_resolved=0,
        )
        payload = RoundResolvedPayload(
            round_no=round_no,
            segment_deltas={},
            participant_deltas={},
            transactions_count=0,
            summary=f"Round {round_no}: 0 transactions, no participants.",
        )
        return ResolveRoundResult(
            new_world=dict(world),
            new_participants=dict(participants),
            outcome=outcome,
            payload=payload,
            warnings=warnings,
        )

    by_segment: dict[str, dict[str, Any]] = {}
    for participant_id, action in market_actions.items():
        if participant_id not in participants:
            warnings.append(f"Ignoring action for unknown participant_id={participant_id}.")
            continue

        try:
            validate_v01_action(action)
        except ValueError:
            warnings.append(
                f"Ignoring unsupported action_type={action.action_type} from participant_id={participant_id}."
            )
            continue

        segment_code = action.target_segment
        if segment_code not in world:
            warnings.append(f"Ignoring action targeting unknown gu_code={segment_code}.")
            continue

        bucket = by_segment.setdefault(
            segment_code,
            {
                "actions": [],
                "buyers": [],
                "sellers": [],
                "buy_count": 0,
                "sell_count": 0,
                "buy_intensity_sum": 0.0,
                "sell_intensity_sum": 0.0,
            },
        )
        bucket["actions"].append(action)
        if action.action_type == "buy":
            bucket["buyers"].append(participant_id)
            bucket["buy_count"] += 1
            bucket["buy_intensity_sum"] += action.confidence
        elif action.action_type == "sell":
            bucket["sellers"].append(participant_id)
            bucket["sell_count"] += 1
            bucket["sell_intensity_sum"] += action.confidence

    updated_world = dict(world)
    updated_participants = dict(participants)

    segment_deltas: dict[str, SegmentDelta] = {}
    participant_capital_changes: dict[str, int] = {}
    participant_holdings_changes: dict[str, int] = {}
    cleared_volume: dict[str, int] = {}
    price_changes: dict[str, float] = {}

    total_matched = 0

    for gu_code in sorted(by_segment):
        bucket = by_segment[gu_code]
        segment = updated_world[gu_code]
        buy_count = int(bucket["buy_count"])
        sell_count = int(bucket["sell_count"])
        total_actions_in_segment = len(bucket["actions"])
        buy_intensity_sum = float(bucket["buy_intensity_sum"])
        sell_intensity_sum = float(bucket["sell_intensity_sum"])

        net_pressure = (buy_intensity_sum - sell_intensity_sum) / max(total_actions_in_segment, 1)
        price_change_pct = _clamp(net_pressure * 0.05, -0.05, 0.05)
        new_median_price = max(1, int(segment.current_median_price * (1 + price_change_pct)))

        matched_transactions = min(
            buy_count,
            sell_count + max(0, int(segment.current_volume * 0.1)),
        )
        volume_change = matched_transactions - segment.current_volume
        new_volume = max(0, segment.current_volume + int(volume_change * 0.1))

        new_sentiment = _clamp(segment.sentiment_index + (net_pressure * 0.1), 0.0, 1.0)
        price_trend: Literal["up", "down", "flat"]
        if price_change_pct > 0.001:
            price_trend = "up"
        elif price_change_pct < -0.001:
            price_trend = "down"
        else:
            price_trend = "flat"

        updated_world[gu_code] = _copy_segment(
            segment,
            median_price=new_median_price,
            volume=new_volume,
            trend=price_trend,
            sentiment_index=new_sentiment,
        )
        segment_deltas[gu_code] = SegmentDelta(
            gu_code=gu_code,
            price_change_pct=price_change_pct,
            volume_change=volume_change,
            new_median_price=new_median_price,
            new_volume=new_volume,
        )
        price_changes[gu_code] = price_change_pct

        buyers = sorted(bucket["buyers"])
        sellers = sorted(bucket["sellers"])
        allow_natural_supply = sell_count == 0

        seller_index = 0
        actual_matches = 0
        for buyer_id in buyers:
            if actual_matches >= matched_transactions:
                break

            buyer = updated_participants[buyer_id]
            if buyer.capital < new_median_price:
                continue

            while seller_index < len(sellers) and updated_participants[sellers[seller_index]].holdings <= 0:
                seller_index += 1
            if seller_index >= len(sellers) and not allow_natural_supply:
                break

            updated_participants[buyer_id] = _copy_participant(
                buyer,
                capital=buyer.capital - new_median_price,
                holdings=buyer.holdings + 1,
            )
            participant_capital_changes[buyer_id] = participant_capital_changes.get(buyer_id, 0) - new_median_price
            participant_holdings_changes[buyer_id] = participant_holdings_changes.get(buyer_id, 0) + 1

            if seller_index < len(sellers):
                seller_id = sellers[seller_index]
                seller = updated_participants[seller_id]
                updated_participants[seller_id] = _copy_participant(
                    seller,
                    capital=seller.capital + new_median_price,
                    holdings=seller.holdings - 1,
                )
                participant_capital_changes[seller_id] = (
                    participant_capital_changes.get(seller_id, 0) + new_median_price
                )
                participant_holdings_changes[seller_id] = participant_holdings_changes.get(seller_id, 0) - 1
                seller_index += 1

            actual_matches += 1
            total_matched += 1

        cleared_volume[gu_code] = actual_matches

    participant_deltas: dict[str, ParticipantDelta] = {}
    for participant_id in sorted(set(participant_capital_changes) | set(participant_holdings_changes)):
        capital_change = participant_capital_changes.get(participant_id, 0)
        holdings_change = participant_holdings_changes.get(participant_id, 0)
        participant_deltas[participant_id] = ParticipantDelta(
            participant_id=participant_id,
            capital_change=capital_change,
            holdings_change=holdings_change,
            new_capital=updated_participants[participant_id].capital,
            new_holdings=updated_participants[participant_id].holdings,
        )

    outcome = RoundOutcome(
        round_no=round_no,
        cleared_volume=cleared_volume,
        price_changes=price_changes,
        governance_applied=[],
        market_actions_resolved=total_matched,
    )

    payload = RoundResolvedPayload(
        round_no=round_no,
        segment_deltas=segment_deltas,
        participant_deltas=participant_deltas,
        transactions_count=total_matched,
        summary=(f"Round {round_no}: {total_matched} transactions, {len(segment_deltas)} segments resolved."),
    )

    return ResolveRoundResult(
        new_world=updated_world,
        new_participants=updated_participants,
        outcome=outcome,
        payload=payload,
        warnings=warnings,
    )


__all__ = ["ResolveRoundResult", "pure_resolve_round"]
