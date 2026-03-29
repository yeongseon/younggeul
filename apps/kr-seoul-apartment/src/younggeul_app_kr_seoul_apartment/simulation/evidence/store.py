from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel, Field


class EvidenceRecord(BaseModel, frozen=True):
    evidence_id: str
    kind: str
    subject_type: str
    subject_id: str
    round_no: int
    payload: dict[str, Any]
    source_event_ids: list[str] = Field(default_factory=list)
    created_at: datetime


class EvidenceStore(Protocol):
    def add(self, record: EvidenceRecord) -> None: ...

    def get(self, evidence_id: str) -> EvidenceRecord | None: ...

    def get_all(self) -> list[EvidenceRecord]: ...

    def get_by_kind(self, kind: str) -> list[EvidenceRecord]: ...

    def get_by_subject(self, subject_type: str, subject_id: str) -> list[EvidenceRecord]: ...

    def count(self) -> int: ...


class InMemoryEvidenceStore:
    def __init__(self) -> None:
        self._records: dict[str, EvidenceRecord] = {}

    def add(self, record: EvidenceRecord) -> None:
        if record.evidence_id in self._records:
            raise ValueError(f"Duplicate evidence_id: {record.evidence_id}")
        self._records[record.evidence_id] = record

    def get(self, evidence_id: str) -> EvidenceRecord | None:
        return self._records.get(evidence_id)

    def get_all(self) -> list[EvidenceRecord]:
        return list(self._records.values())

    def get_by_kind(self, kind: str) -> list[EvidenceRecord]:
        return [record for record in self._records.values() if record.kind == kind]

    def get_by_subject(self, subject_type: str, subject_id: str) -> list[EvidenceRecord]:
        return [
            record
            for record in self._records.values()
            if record.subject_type == subject_type and record.subject_id == subject_id
        ]

    def count(self) -> int:
        return len(self._records)
