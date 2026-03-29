from __future__ import annotations

from datetime import datetime, timezone
from importlib import import_module
from typing import Any

import pytest
from pydantic import ValidationError

evidence_store_module = import_module("younggeul_app_kr_seoul_apartment.simulation.evidence.store")

EvidenceRecord = evidence_store_module.EvidenceRecord
InMemoryEvidenceStore = evidence_store_module.InMemoryEvidenceStore


def _make_record(**overrides: Any) -> EvidenceRecord:
    payload = {
        "evidence_id": "ev-001",
        "kind": "simulation_fact",
        "subject_type": "simulation",
        "subject_id": "run-001",
        "round_no": 3,
        "payload": {"total_rounds": 3},
        "source_event_ids": ["evt-123"],
        "created_at": datetime(2026, 3, 29, 12, 0, 0, tzinfo=timezone.utc),
    }
    payload.update(overrides)
    return EvidenceRecord(**payload)


def test_add_and_get() -> None:
    store = InMemoryEvidenceStore()
    record = _make_record()

    store.add(record)

    assert store.get("ev-001") == record


def test_get_nonexistent() -> None:
    store = InMemoryEvidenceStore()

    assert store.get("missing") is None


def test_add_duplicate_raises() -> None:
    store = InMemoryEvidenceStore()
    record = _make_record()
    store.add(record)

    with pytest.raises(ValueError, match="Duplicate evidence_id: ev-001"):
        store.add(record)


def test_get_all() -> None:
    store = InMemoryEvidenceStore()
    first = _make_record(evidence_id="ev-001")
    second = _make_record(evidence_id="ev-002", kind="segment_fact", subject_type="segment", subject_id="11680")
    store.add(first)
    store.add(second)

    assert store.get_all() == [first, second]


def test_get_by_kind() -> None:
    store = InMemoryEvidenceStore()
    first = _make_record(evidence_id="ev-001", kind="segment_fact")
    second = _make_record(evidence_id="ev-002", kind="segment_fact")
    third = _make_record(evidence_id="ev-003", kind="round_fact")
    store.add(first)
    store.add(second)
    store.add(third)

    assert store.get_by_kind("segment_fact") == [first, second]


def test_get_by_subject() -> None:
    store = InMemoryEvidenceStore()
    first = _make_record(evidence_id="ev-001", subject_type="segment", subject_id="11680")
    second = _make_record(evidence_id="ev-002", subject_type="segment", subject_id="11650")
    third = _make_record(evidence_id="ev-003", subject_type="round", subject_id="round-3")
    store.add(first)
    store.add(second)
    store.add(third)

    assert store.get_by_subject("segment", "11680") == [first]


def test_count() -> None:
    store = InMemoryEvidenceStore()
    store.add(_make_record(evidence_id="ev-001"))
    store.add(_make_record(evidence_id="ev-002"))

    assert store.count() == 2


def test_empty_store() -> None:
    store = InMemoryEvidenceStore()

    assert store.count() == 0
    assert store.get_all() == []
    assert store.get_by_kind("simulation_fact") == []
    assert store.get_by_subject("segment", "11680") == []


def test_evidence_record_frozen() -> None:
    record = _make_record()

    with pytest.raises(ValidationError):
        record.kind = "round_fact"
