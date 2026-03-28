import sqlite3
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from younggeul_core.evidence import (
    CLAIMS_TABLE_SQL,
    EVIDENCE_TABLE_SQL,
    GATE_RESULTS_TABLE_SQL,
    ClaimRecord,
    EvidenceRecord,
    GateResult,
)


def _evidence_payload() -> dict:
    return {
        "evidence_id": "3f8a4e6a-ea2b-442d-b593-5f9e8cd7ad4f",
        "dataset_snapshot_id": "a" * 64,
        "source_table": "gold_district_monthly",
        "source_row_hash": "b" * 64,
        "field_name": "median_price",
        "field_value": "1500000000",
        "field_type": "int",
        "gu_code": "11680",
        "period": "2025-03",
        "created_at": datetime(2026, 3, 28, 1, 0, tzinfo=timezone.utc),
    }


def _claim_payload() -> dict:
    return {
        "claim_id": "4f510cae-b5f9-4fba-b8f9-a236f2f4d876",
        "run_id": "6d93ff94-f4d8-4d28-b8a5-0186d2fce623",
        "claim_json": {
            "metric": "median_price",
            "gu": "강남구",
            "period": "2025-03",
            "value": 1500000000,
            "direction": "up",
        },
        "evidence_ids": ["3f8a4e6a-ea2b-442d-b593-5f9e8cd7ad4f"],
        "gate_status": "pending",
        "gate_checked_at": None,
        "repair_count": 0,
        "repair_notes": None,
        "created_at": datetime(2026, 3, 28, 1, 5, tzinfo=timezone.utc),
    }


def _gate_result_payload() -> dict:
    return {
        "claim_id": "4f510cae-b5f9-4fba-b8f9-a236f2f4d876",
        "status": "passed",
        "checked_evidence_ids": ["3f8a4e6a-ea2b-442d-b593-5f9e8cd7ad4f"],
        "checked_at": datetime(2026, 3, 28, 1, 10, tzinfo=timezone.utc),
    }


def _extract_columns(create_sql: str) -> set[str]:
    columns: set[str] = set()
    for raw_line in create_sql.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("CREATE TABLE") or line in {"(", ");"}:
            continue
        column_name = line.split()[0].rstrip(",")
        if column_name in {"PRIMARY", "CHECK"}:
            continue
        columns.add(column_name)
    return columns


def test_evidence_record_round_trip() -> None:
    payload = _evidence_payload()
    record = EvidenceRecord.model_validate(payload)
    restored = EvidenceRecord.model_validate(record.model_dump())
    assert restored == record


def test_evidence_record_rejects_invalid_dataset_snapshot_id() -> None:
    payload = _evidence_payload()
    payload["dataset_snapshot_id"] = "not-a-sha"
    with pytest.raises(ValidationError):
        EvidenceRecord.model_validate(payload)


def test_evidence_record_rejects_invalid_evidence_id_uuid() -> None:
    payload = _evidence_payload()
    payload["evidence_id"] = "invalid-uuid"
    with pytest.raises(ValidationError):
        EvidenceRecord.model_validate(payload)


def test_claim_record_round_trip() -> None:
    payload = _claim_payload()
    record = ClaimRecord.model_validate(payload)
    restored = ClaimRecord.model_validate(record.model_dump())
    assert restored == record


def test_claim_record_repair_count_rejects_values_over_two() -> None:
    payload = _claim_payload()
    payload["repair_count"] = 3
    with pytest.raises(ValidationError):
        ClaimRecord.model_validate(payload)


@pytest.mark.parametrize("status", ["pending", "passed", "failed", "repaired"])
def test_claim_record_gate_status_allows_required_states(status: str) -> None:
    payload = _claim_payload()
    payload["gate_status"] = status
    record = ClaimRecord.model_validate(payload)
    assert record.gate_status == status


def test_claim_record_gate_status_rejects_unknown_state() -> None:
    payload = _claim_payload()
    payload["gate_status"] = "unknown"
    with pytest.raises(ValidationError):
        ClaimRecord.model_validate(payload)


def test_claim_json_accepts_arbitrary_nested_dict() -> None:
    payload = _claim_payload()
    payload["claim_json"] = {
        "metric": {"name": "median_price", "units": "KRW"},
        "axes": ["period", "gu"],
        "window": {"start": "2025-01", "end": "2025-03"},
        "confidence": 0.93,
    }
    record = ClaimRecord.model_validate(payload)
    assert record.claim_json["metric"]["name"] == "median_price"


def test_claim_record_evidence_ids_is_list_of_strings() -> None:
    payload = _claim_payload()
    payload["evidence_ids"] = "not-a-list"
    with pytest.raises(ValidationError):
        ClaimRecord.model_validate(payload)


def test_gate_result_passed_and_failed_scenarios() -> None:
    passed_payload = _gate_result_payload()
    passed = GateResult.model_validate(passed_payload)
    failed_payload = _gate_result_payload()
    failed_payload["status"] = "failed"
    failed = GateResult.model_validate(failed_payload)
    assert passed.status == "passed"
    assert failed.status == "failed"


def test_gate_result_with_mismatches_populated() -> None:
    payload = _gate_result_payload()
    payload["status"] = "failed"
    payload["mismatches"] = [
        {
            "evidence_id": "3f8a4e6a-ea2b-442d-b593-5f9e8cd7ad4f",
            "expected": "1500000000",
            "actual": "1300000000",
            "tolerance": 0.01,
        }
    ]
    result = GateResult.model_validate(payload)
    assert result.mismatches[0]["actual"] == "1300000000"


def test_sql_table_statements_execute_in_sqlite() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(EVIDENCE_TABLE_SQL)
        connection.executescript(CLAIMS_TABLE_SQL)
        connection.executescript(GATE_RESULTS_TABLE_SQL)
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('evidence_records', 'claim_records', 'gate_results')"
        ).fetchall()
    finally:
        connection.close()
    assert {row[0] for row in rows} == {"evidence_records", "claim_records", "gate_results"}


def test_pydantic_field_names_match_sql_columns() -> None:
    assert set(EvidenceRecord.model_fields) == _extract_columns(EVIDENCE_TABLE_SQL)
    assert set(ClaimRecord.model_fields) == _extract_columns(CLAIMS_TABLE_SQL)
    assert set(GateResult.model_fields) == _extract_columns(GATE_RESULTS_TABLE_SQL)
