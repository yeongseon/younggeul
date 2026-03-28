from datetime import date, datetime
from pathlib import Path
import subprocess
from typing import Callable

import pytest
from pydantic import BaseModel, ValidationError

from younggeul_core.state.simulation import (
    ActionProposal,
    ParticipantState,
    ReportClaim,
    RoundOutcome,
    RunMeta,
    ScenarioSpec,
    SegmentState,
    Shock,
    SimulationState,
    SnapshotRef,
)


def build_run_meta() -> RunMeta:
    return RunMeta(
        run_id="14f27ee1-afaa-4a7b-bf2a-10d37fd26a6b",
        run_name="Seoul Baseline",
        created_at=datetime(2026, 3, 1, 9, 30, 0),
        model_id="gpt-5.3-codex",
        config_hash="cfg-123",
    )


def build_snapshot_ref() -> SnapshotRef:
    return SnapshotRef(
        dataset_snapshot_id="a" * 64,
        created_at=datetime(2026, 3, 1, 9, 35, 0),
        table_count=4,
    )


def build_shock() -> Shock:
    return Shock(
        shock_type="interest_rate",
        description="Rate increased by 0.5%",
        magnitude=0.5,
        target_segments=["11680", "11650"],
    )


def build_scenario_spec() -> ScenarioSpec:
    return ScenarioSpec(
        scenario_name="Rate hike in southern Seoul",
        target_gus=["강남구", "서초구"],
        target_period_start=date(2026, 1, 1),
        target_period_end=date(2026, 3, 31),
        shocks=[build_shock()],
    )


def build_segment_state() -> SegmentState:
    return SegmentState(
        gu_code="11680",
        gu_name="강남구",
        current_median_price=1_800_000_000,
        current_volume=240,
        price_trend="up",
        sentiment_index=0.72,
        supply_pressure=-0.12,
    )


def build_participant_state() -> ParticipantState:
    return ParticipantState(
        participant_id="buyer-01",
        role="buyer",
        capital=900_000_000,
        holdings=1,
        sentiment="bullish",
        risk_tolerance=0.64,
    )


def build_action_proposal() -> ActionProposal:
    return ActionProposal(
        agent_id="buyer-agent",
        round_no=2,
        action_type="buy",
        target_segment="11680",
        confidence=0.88,
        reasoning_summary="Demand remains strong in high-income districts.",
        proposed_value={"units": 2, "price_cap": 1_900_000_000},
    )


def build_round_outcome() -> RoundOutcome:
    return RoundOutcome(
        round_no=2,
        cleared_volume={"11680": 40, "11650": 18},
        price_changes={"11680": 0.013, "11650": 0.007},
        governance_applied=["rate_plus_0_5"],
        market_actions_resolved=58,
    )


def build_report_claim() -> ReportClaim:
    return ReportClaim(
        claim_id="claim-001",
        claim_json={"district": "강남구", "direction": "up", "change_pct": 1.3},
        evidence_ids=["ev-100", "ev-101"],
        gate_status="pending",
        repair_count=1,
    )


def build_simulation_state() -> SimulationState:
    return {
        "run_meta": build_run_meta(),
        "snapshot": build_snapshot_ref(),
        "scenario": build_scenario_spec(),
        "round_no": 2,
        "max_rounds": 8,
        "world": {"11680": build_segment_state()},
        "participants": {"buyer-01": build_participant_state()},
        "governance_actions": {"ga-1": build_action_proposal()},
        "market_actions": {"ma-1": build_action_proposal()},
        "last_outcome": build_round_outcome(),
        "event_refs": ["event-01"],
        "evidence_refs": ["ev-100", "ev-101"],
        "report_claims": [build_report_claim()],
        "warnings": ["sample warning"],
    }


def test_run_meta_valid_model() -> None:
    model = build_run_meta()
    assert model.run_name == "Seoul Baseline"


def test_snapshot_ref_valid_model() -> None:
    model = build_snapshot_ref()
    assert model.table_count == 4


def test_shock_valid_model() -> None:
    model = build_shock()
    assert model.shock_type == "interest_rate"


def test_scenario_spec_valid_model() -> None:
    model = build_scenario_spec()
    assert model.target_gus == ["강남구", "서초구"]


def test_segment_state_valid_model() -> None:
    model = build_segment_state()
    assert model.price_trend == "up"


def test_participant_state_valid_model() -> None:
    model = build_participant_state()
    assert model.role == "buyer"


def test_action_proposal_valid_model() -> None:
    model = build_action_proposal()
    assert model.action_type == "buy"


def test_round_outcome_valid_model() -> None:
    model = build_round_outcome()
    assert model.market_actions_resolved == 58


def test_report_claim_valid_model() -> None:
    model = build_report_claim()
    assert model.repair_count == 1


def test_simulation_state_typed_dict_construction_with_all_fields() -> None:
    state = build_simulation_state()
    assert state["round_no"] == 2
    assert set(state.keys()) == {
        "run_meta",
        "snapshot",
        "scenario",
        "round_no",
        "max_rounds",
        "world",
        "participants",
        "governance_actions",
        "market_actions",
        "last_outcome",
        "event_refs",
        "evidence_refs",
        "report_claims",
        "warnings",
    }


def test_snapshot_ref_rejects_non_hex_or_non_64_char_id() -> None:
    with pytest.raises(ValidationError):
        _ = SnapshotRef(dataset_snapshot_id="abc123", created_at=datetime(2026, 3, 1, 9, 35, 0), table_count=4)

    with pytest.raises(ValidationError):
        _ = SnapshotRef(dataset_snapshot_id="g" * 64, created_at=datetime(2026, 3, 1, 9, 35, 0), table_count=4)


@pytest.mark.parametrize("magnitude", [-1.01, 1.01])
def test_shock_magnitude_range_validation(magnitude: float) -> None:
    with pytest.raises(ValidationError):
        _ = Shock(shock_type="demand", description="invalid magnitude", magnitude=magnitude)


def test_scenario_spec_rejects_target_period_end_before_start() -> None:
    with pytest.raises(ValidationError):
        _ = ScenarioSpec(
            scenario_name="invalid-period",
            target_gus=["강남구"],
            target_period_start=date(2026, 4, 1),
            target_period_end=date(2026, 3, 1),
        )


def test_report_claim_rejects_repair_count_over_two() -> None:
    with pytest.raises(ValidationError):
        _ = ReportClaim(
            claim_id="claim-overflow",
            claim_json={"district": "강남구"},
            evidence_ids=["ev-1"],
            repair_count=3,
        )


@pytest.mark.parametrize("confidence", [-0.1, 1.1])
def test_action_proposal_confidence_range_validation(confidence: float) -> None:
    with pytest.raises(ValidationError):
        _ = ActionProposal(
            agent_id="agent-x",
            round_no=1,
            action_type="hold",
            target_segment="11680",
            confidence=confidence,
            reasoning_summary="invalid confidence",
        )


def test_nested_simulation_state_holds_segment_and_participant_models() -> None:
    state = build_simulation_state()
    assert state["world"]["11680"].gu_name == "강남구"
    assert state["participants"]["buyer-01"].sentiment == "bullish"


@pytest.mark.parametrize(
    "builder",
    [
        build_run_meta,
        build_snapshot_ref,
        build_shock,
        build_scenario_spec,
        build_segment_state,
        build_participant_state,
        build_action_proposal,
        build_round_outcome,
        build_report_claim,
    ],
)
def test_json_round_trip_for_all_base_models(builder: Callable[[], BaseModel]) -> None:
    model = builder()
    model_cls = type(model)
    as_json = model.model_dump_json()
    restored = model_cls.model_validate_json(as_json)
    assert restored == model


def test_forbidden_add_token_not_present_in_state_or_contract_tests() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    token = "add" + "_messages"
    result = subprocess.run(
        [
            "grep",
            "-r",
            "--include=*.py",
            "--binary-files=without-match",
            token,
            str(repo_root / "core/src/younggeul_core/state"),
            str(repo_root / "core/tests/contract"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1


def test_forbidden_basemessage_token_not_present_in_state_or_contract_tests() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    token = "Base" + "Message"
    result = subprocess.run(
        [
            "grep",
            "-r",
            "--include=*.py",
            "--binary-files=without-match",
            token,
            str(repo_root / "core/src/younggeul_core/state"),
            str(repo_root / "core/tests/contract"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
