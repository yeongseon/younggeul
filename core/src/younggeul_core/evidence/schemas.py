from datetime import datetime
import re
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")


class EvidenceRecord(BaseModel):
    evidence_id: str
    dataset_snapshot_id: str
    source_table: str
    source_row_hash: str
    field_name: str
    field_value: str
    field_type: Literal["int", "float", "str", "date", "bool"]
    gu_code: str | None = None
    period: str | None = None
    created_at: datetime

    model_config = ConfigDict(frozen=True)

    @field_validator("evidence_id")
    @classmethod
    def validate_evidence_id_uuid(cls, value: str) -> str:
        UUID(value)
        return value

    @field_validator("dataset_snapshot_id", "source_row_hash")
    @classmethod
    def validate_sha256_hex(cls, value: str) -> str:
        if not _SHA256_HEX_RE.fullmatch(value):
            raise ValueError("must be a 64-character lowercase hex SHA-256 string")
        return value


class ClaimRecord(BaseModel):
    claim_id: str
    run_id: str
    claim_json: dict[str, Any]
    evidence_ids: list[str]
    gate_status: Literal["pending", "passed", "failed", "repaired"] = "pending"
    gate_checked_at: datetime | None = None
    repair_count: int = 0
    repair_notes: str | None = None
    created_at: datetime

    model_config = ConfigDict(frozen=True)

    @field_validator("claim_id", "run_id")
    @classmethod
    def validate_uuid(cls, value: str) -> str:
        UUID(value)
        return value

    @field_validator("repair_count")
    @classmethod
    def validate_repair_count(cls, value: int) -> int:
        if value > 2:
            raise ValueError("repair_count must be <= 2")
        return value


class GateResult(BaseModel):
    claim_id: str
    status: Literal["passed", "failed"]
    checked_evidence_ids: list[str]
    mismatches: list[dict[str, Any]] = Field(default_factory=list)
    checked_at: datetime

    model_config = ConfigDict(frozen=True)

    @field_validator("claim_id")
    @classmethod
    def validate_claim_id_uuid(cls, value: str) -> str:
        UUID(value)
        return value
