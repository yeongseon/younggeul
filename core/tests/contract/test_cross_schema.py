import re
from datetime import date, datetime, timezone
from decimal import Decimal
from statistics import median
from typing import get_args, get_type_hints
from uuid import uuid4

import pytest
from pydantic import BaseModel, ValidationError, field_validator

from younggeul_core.evidence import ClaimRecord, EvidenceRecord, GateResult
from younggeul_core.state import (
    BronzeAptTransaction,
    BronzeInterestRate,
    BronzeMigration,
    GoldDistrictMonthlyMetrics,
    ReportClaim,
    RunMeta,
    ScenarioSpec,
    SegmentState,
    SimulationState,
    SilverAptTransaction,
    SnapshotRef,
)
from younggeul_core.storage import SnapshotManifest, SnapshotTableEntry


class BenchmarkScenarioContract(BaseModel):
    dataset_snapshot_id: str

    @field_validator("dataset_snapshot_id")
    @classmethod
    def validate_dataset_snapshot_id(cls, value: str) -> str:
        if not re.fullmatch(r"^[0-9a-fA-F]{64}$", value):
            raise ValueError("dataset_snapshot_id must be a 64-character hex SHA-256 string")
        return value


def _ts() -> datetime:
    return datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc)


def _snapshot_id() -> str:
    return "a" * 64


def _bronze_apt() -> BronzeAptTransaction:
    return BronzeAptTransaction(
        ingest_timestamp=_ts(),
        source_id="molit_apt_trade_v2",
        deal_amount="1200000000",
        deal_year="2026",
        deal_month="01",
        deal_day="15",
        dong="역삼동",
        area_exclusive="84.99",
        floor="12",
        apt_name="래미안",
        regional_code="11680",
        cancel_deal_type="N",
        req_gbn="중개거래",
        jibun="123-45",
        road_name="테헤란로",
    )


def test_bronze_apt_fixture_is_valid_for_cross_schema_derivation() -> None:
    bronze = _bronze_apt()
    assert bronze.regional_code == "11680"


def _silver_apt() -> SilverAptTransaction:
    return SilverAptTransaction(
        transaction_id="tx-1",
        deal_amount=1_200_000_000,
        deal_date=date(2026, 1, 15),
        build_year=2018,
        dong_code="1168010300",
        dong_name="역삼동",
        gu_code="11680",
        gu_name="강남구",
        apt_name="래미안",
        floor=12,
        area_exclusive_m2=Decimal("84.99"),
        jibun="123-45",
        road_name="테헤란로",
        source_id="molit_apt_trade_v2",
        ingest_timestamp=_ts(),
    )


@pytest.mark.parametrize(
    "field_name",
    [
        "deal_amount",
        "deal_year",
        "deal_month",
        "deal_day",
        "dong",
        "area_exclusive",
        "floor",
        "apt_name",
        "regional_code",
        "cancel_deal_type",
        "req_gbn",
        "jibun",
        "road_name",
    ],
)
def test_bronze_apt_has_fields_required_for_silver_derivation(field_name: str) -> None:
    assert field_name in BronzeAptTransaction.model_fields


@pytest.mark.parametrize("field_name", ["date", "rate_value", "rate_type"])
def test_bronze_interest_rate_has_fields_required_for_silver_derivation(field_name: str) -> None:
    assert field_name in BronzeInterestRate.model_fields


@pytest.mark.parametrize(
    "field_name",
    ["year", "month", "region_code", "region_name", "in_count", "out_count", "net_count"],
)
def test_bronze_migration_has_fields_required_for_silver_derivation(field_name: str) -> None:
    assert field_name in BronzeMigration.model_fields


def test_silver_gu_code_contract_compatible_with_gold_gu_code() -> None:
    silver = _silver_apt()
    gold = GoldDistrictMonthlyMetrics(
        gu_code=silver.gu_code,
        gu_name=silver.gu_name,
        period="2026-01",
        sale_count=1,
        avg_price=silver.deal_amount,
        median_price=silver.deal_amount,
        min_price=silver.deal_amount,
        max_price=silver.deal_amount,
        price_per_pyeong_avg=46_600_000,
    )
    assert re.fullmatch(r"^\d{5}$", silver.gu_code)
    assert gold.gu_code == silver.gu_code


def test_silver_deal_amounts_aggregate_to_gold_price_metrics_as_int_krw() -> None:
    amounts = [1_200_000_000, 1_500_000_000, 900_000_000]
    aggregated = GoldDistrictMonthlyMetrics(
        gu_code="11680",
        gu_name="강남구",
        period="2026-01",
        sale_count=len(amounts),
        avg_price=sum(amounts) // len(amounts),
        median_price=int(median(amounts)),
        min_price=min(amounts),
        max_price=max(amounts),
        price_per_pyeong_avg=60_000_000,
    )
    assert isinstance(aggregated.avg_price, int)
    assert isinstance(aggregated.median_price, int)
    assert isinstance(aggregated.min_price, int)
    assert isinstance(aggregated.max_price, int)


def test_silver_deal_date_groups_to_gold_period_yyyy_mm() -> None:
    silver = _silver_apt()
    period = silver.deal_date.strftime("%Y-%m")
    model = GoldDistrictMonthlyMetrics(
        gu_code=silver.gu_code,
        gu_name=silver.gu_name,
        period=period,
        sale_count=1,
        avg_price=silver.deal_amount,
        median_price=silver.deal_amount,
        min_price=silver.deal_amount,
        max_price=silver.deal_amount,
        price_per_pyeong_avg=46_600_000,
    )
    assert model.period == "2026-01"


def test_silver_area_exclusive_decimal_supports_price_per_pyeong_calculation() -> None:
    silver = _silver_apt()
    pyeong = silver.area_exclusive_m2 / Decimal("3.3058")
    price_per_pyeong = silver.deal_amount / pyeong
    assert isinstance(silver.area_exclusive_m2, Decimal)
    assert int(price_per_pyeong) > 0


def test_simulation_state_snapshot_type_is_snapshot_ref() -> None:
    hints = get_type_hints(SimulationState)
    assert hints["snapshot"] is SnapshotRef


def test_snapshot_ref_and_snapshot_manifest_accept_shared_snapshot_id_format() -> None:
    snapshot_id = _snapshot_id()
    ref = SnapshotRef(dataset_snapshot_id=snapshot_id, created_at=_ts(), table_count=2)
    table_hashes = {"gold_district_monthly_metrics": "b" * 64}
    computed = SnapshotManifest.compute_snapshot_id(table_hashes)
    manifest = SnapshotManifest(
        dataset_snapshot_id=computed,
        created_at=_ts(),
        table_entries=[
            SnapshotTableEntry(
                table_name="gold_district_monthly_metrics",
                table_hash="b" * 64,
                record_count=11,
                schema_version="1.0.0",
            )
        ],
    )
    assert len(ref.dataset_snapshot_id) == 64
    assert len(manifest.dataset_snapshot_id) == 64


def test_evidence_record_and_claim_record_reference_types_are_compatible() -> None:
    evidence_id = str(uuid4())
    evidence = EvidenceRecord(
        evidence_id=evidence_id,
        dataset_snapshot_id=_snapshot_id(),
        source_table="gold_district_monthly_metrics",
        source_row_hash="b" * 64,
        field_name="median_price",
        field_value="1200000000",
        field_type="int",
        created_at=_ts(),
    )
    claim = ClaimRecord(
        claim_id=str(uuid4()),
        run_id=str(uuid4()),
        claim_json={"metric": "median_price"},
        evidence_ids=[evidence.evidence_id],
        created_at=_ts(),
    )
    assert isinstance(evidence.evidence_id, str)
    assert all(isinstance(item, str) for item in claim.evidence_ids)


def test_evidence_and_snapshot_manifest_use_compatible_dataset_snapshot_id_format() -> None:
    snapshot_id = _snapshot_id()
    evidence = EvidenceRecord(
        evidence_id=str(uuid4()),
        dataset_snapshot_id=snapshot_id,
        source_table="gold_district_monthly_metrics",
        source_row_hash="b" * 64,
        field_name="sale_count",
        field_value="10",
        field_type="int",
        created_at=_ts(),
    )
    manifest = SnapshotManifest(
        dataset_snapshot_id=snapshot_id,
        created_at=_ts(),
        table_entries=[
            SnapshotTableEntry(
                table_name="gold_district_monthly_metrics",
                table_hash="b" * 64,
                record_count=10,
                schema_version="1.0.0",
            )
        ],
    )
    assert evidence.dataset_snapshot_id == manifest.dataset_snapshot_id


def test_claim_gate_status_literals_cover_gate_result_status_literals() -> None:
    claim_statuses = set(get_args(ClaimRecord.model_fields["gate_status"].annotation))
    gate_result_statuses = set(get_args(GateResult.model_fields["status"].annotation))
    assert gate_result_statuses.issubset(claim_statuses)


def test_report_claim_and_claim_record_share_claim_json_and_evidence_ids_contract() -> None:
    report = ReportClaim(claim_id="claim-1", claim_json={"metric": "avg_price"}, evidence_ids=["ev-1"])
    claim = ClaimRecord(
        claim_id=str(uuid4()),
        run_id=str(uuid4()),
        claim_json={"metric": "avg_price"},
        evidence_ids=["ev-1"],
        created_at=_ts(),
    )
    assert isinstance(report.claim_json, dict)
    assert isinstance(report.evidence_ids, list)
    assert isinstance(claim.evidence_ids, list)


def test_report_claim_and_claim_record_gate_status_literals_match() -> None:
    report_statuses = set(get_args(ReportClaim.model_fields["gate_status"].annotation))
    claim_statuses = set(get_args(ClaimRecord.model_fields["gate_status"].annotation))
    assert report_statuses == claim_statuses


def test_benchmark_scenario_and_snapshot_manifest_share_snapshot_id_format() -> None:
    snapshot_id = _snapshot_id()
    benchmark = BenchmarkScenarioContract(dataset_snapshot_id=snapshot_id)
    manifest = SnapshotManifest(
        dataset_snapshot_id=snapshot_id,
        created_at=_ts(),
        table_entries=[
            SnapshotTableEntry(
                table_name="gold_district_monthly_metrics",
                table_hash="b" * 64,
                record_count=1,
                schema_version="1.0.0",
            )
        ],
    )
    assert benchmark.dataset_snapshot_id == manifest.dataset_snapshot_id


def test_benchmark_scenario_and_snapshot_manifest_reject_non_sha256_ids() -> None:
    with pytest.raises(ValidationError):
        _ = BenchmarkScenarioContract(dataset_snapshot_id="not-a-sha")
    with pytest.raises(ValidationError):
        _ = SnapshotManifest(dataset_snapshot_id="not-a-sha", created_at=_ts(), table_entries=[])


def test_round_trip_full_simulation_state_nested_models_via_json() -> None:
    state: SimulationState = {
        "run_meta": RunMeta(
            run_id="run-1",
            run_name="baseline",
            created_at=_ts(),
            model_id="gpt-5.3-codex",
        ),
        "snapshot": SnapshotRef(dataset_snapshot_id=_snapshot_id(), created_at=_ts(), table_count=2),
        "scenario": ScenarioSpec(
            scenario_name="baseline",
            target_gus=["11680"],
            target_period_start=date(2026, 1, 1),
            target_period_end=date(2026, 1, 31),
            shocks=[],
        ),
        "round_no": 1,
        "max_rounds": 3,
        "world": {
            "11680": SegmentState(
                gu_code="11680",
                gu_name="강남구",
                current_median_price=1_500_000_000,
                current_volume=120,
                price_trend="flat",
                sentiment_index=0.7,
                supply_pressure=0.0,
            )
        },
        "participants": {},
        "governance_actions": {},
        "market_actions": {},
        "last_outcome": None,
        "event_refs": ["evt-1"],
        "evidence_refs": ["ev-1"],
        "report_claims": [
            ReportClaim(
                claim_id="claim-1",
                claim_json={"metric": "median_price", "direction": "flat"},
                evidence_ids=["ev-1"],
                gate_status="pending",
                repair_count=0,
            )
        ],
        "warnings": [],
    }

    world_dumps = {code: segment.model_dump_json() for code, segment in state["world"].items()}
    report_claim_dumps = [claim.model_dump_json() for claim in state["report_claims"]]
    run_meta_dump = state["run_meta"].model_dump_json()
    snapshot_dump = state["snapshot"].model_dump_json()
    scenario_dump = state["scenario"].model_dump_json()
    restored: SimulationState = {
        "run_meta": RunMeta.model_validate_json(run_meta_dump),
        "snapshot": SnapshotRef.model_validate_json(snapshot_dump),
        "scenario": ScenarioSpec.model_validate_json(scenario_dump),
        "world": {code: SegmentState.model_validate_json(payload) for code, payload in world_dumps.items()},
        "report_claims": [ReportClaim.model_validate_json(payload) for payload in report_claim_dumps],
        "round_no": state["round_no"],
        "max_rounds": state["max_rounds"],
        "participants": state["participants"],
        "governance_actions": state["governance_actions"],
        "market_actions": state["market_actions"],
        "last_outcome": state["last_outcome"],
        "event_refs": state["event_refs"],
        "evidence_refs": state["evidence_refs"],
        "warnings": state["warnings"],
    }
    assert restored == state


def test_round_trip_evidence_claim_gate_chain_reference_integrity() -> None:
    evidence = EvidenceRecord(
        evidence_id=str(uuid4()),
        dataset_snapshot_id=_snapshot_id(),
        source_table="gold_district_monthly_metrics",
        source_row_hash="b" * 64,
        field_name="avg_price",
        field_value="1500000000",
        field_type="int",
        created_at=_ts(),
    )
    claim = ClaimRecord(
        claim_id=str(uuid4()),
        run_id=str(uuid4()),
        claim_json={"metric": "avg_price", "value": 1_500_000_000},
        evidence_ids=[evidence.evidence_id],
        gate_status="passed",
        created_at=_ts(),
    )
    gate = GateResult(
        claim_id=claim.claim_id,
        status="passed",
        checked_evidence_ids=[evidence.evidence_id],
        checked_at=_ts(),
    )
    assert claim.evidence_ids == gate.checked_evidence_ids
    assert gate.claim_id == claim.claim_id


def test_snapshot_manifest_validate_integrity_works_with_compute_snapshot_id() -> None:
    table_hashes = {
        "gold_district_monthly_metrics": "a" * 64,
        "silver_apt_transaction": "b" * 64,
    }
    snapshot_id = SnapshotManifest.compute_snapshot_id(table_hashes)
    manifest = SnapshotManifest(
        dataset_snapshot_id=snapshot_id,
        created_at=_ts(),
        table_entries=[
            SnapshotTableEntry(
                table_name="gold_district_monthly_metrics",
                table_hash="a" * 64,
                record_count=100,
                schema_version="1.0.0",
            ),
            SnapshotTableEntry(
                table_name="silver_apt_transaction",
                table_hash="b" * 64,
                record_count=200,
                schema_version="1.0.0",
            ),
        ],
    )
    assert manifest.validate_integrity() is True


def test_claim_record_allows_nonexistent_evidence_references_as_runtime_concern() -> None:
    claim = ClaimRecord(
        claim_id=str(uuid4()),
        run_id=str(uuid4()),
        claim_json={"metric": "median_price"},
        evidence_ids=["non-existent-evidence-id"],
        created_at=_ts(),
    )
    assert claim.evidence_ids == ["non-existent-evidence-id"]


@pytest.mark.parametrize("repair_count", [0, 1, 2])
def test_report_claim_and_claim_record_accept_repair_count_up_to_two(repair_count: int) -> None:
    report = ReportClaim(
        claim_id="claim-1",
        claim_json={"metric": "avg_price"},
        evidence_ids=["ev-1"],
        repair_count=repair_count,
    )
    claim = ClaimRecord(
        claim_id=str(uuid4()),
        run_id=str(uuid4()),
        claim_json={"metric": "avg_price"},
        evidence_ids=["ev-1"],
        repair_count=repair_count,
        created_at=_ts(),
    )
    assert report.repair_count == repair_count
    assert claim.repair_count == repair_count


def test_report_claim_and_claim_record_reject_repair_count_over_two() -> None:
    with pytest.raises(ValidationError):
        _ = ReportClaim(claim_id="claim-1", claim_json={"k": "v"}, evidence_ids=["ev-1"], repair_count=3)
    with pytest.raises(ValidationError):
        _ = ClaimRecord(
            claim_id=str(uuid4()),
            run_id=str(uuid4()),
            claim_json={"k": "v"},
            evidence_ids=["ev-1"],
            repair_count=3,
            created_at=_ts(),
        )


@pytest.mark.parametrize("bad_snapshot_id", ["abc123", "g" * 64])
def test_snapshot_ref_and_snapshot_manifest_reject_same_bad_snapshot_ids(bad_snapshot_id: str) -> None:
    with pytest.raises(ValidationError):
        _ = SnapshotRef(dataset_snapshot_id=bad_snapshot_id, created_at=_ts(), table_count=1)
    with pytest.raises(ValidationError):
        _ = SnapshotManifest(dataset_snapshot_id=bad_snapshot_id, created_at=_ts(), table_entries=[])
