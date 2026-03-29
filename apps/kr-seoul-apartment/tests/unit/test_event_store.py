from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from younggeul_app_kr_seoul_apartment.simulation.event_store import FileEventStore, InMemoryEventStore
from younggeul_app_kr_seoul_apartment.simulation.events import EventStore, SimulationEvent


def _make_event(**overrides: Any) -> SimulationEvent:
    payload = {
        "event_id": "evt-001",
        "run_id": "run-001",
        "round_no": 0,
        "event_type": "WORLD_INITIALIZED",
        "timestamp": datetime(2026, 3, 29, 12, 0, 0, tzinfo=timezone.utc),
        "payload": {},
    }
    payload.update(overrides)
    return SimulationEvent(**payload)


class TestSimulationEvent:
    def test_creates_valid_event(self) -> None:
        event = _make_event()

        assert event.event_id == "evt-001"
        assert event.run_id == "run-001"
        assert event.round_no == 0
        assert event.event_type == "WORLD_INITIALIZED"
        assert event.timestamp == datetime(2026, 3, 29, 12, 0, 0, tzinfo=timezone.utc)

    def test_model_is_immutable(self) -> None:
        event = _make_event()

        with pytest.raises(ValidationError):
            event.event_type = "ROUND_STARTED"

    def test_round_no_must_be_greater_than_or_equal_to_zero(self) -> None:
        with pytest.raises(ValidationError):
            _make_event(round_no=-1)

    def test_payload_defaults_to_empty_dict(self) -> None:
        event = SimulationEvent(
            event_id="evt-002",
            run_id="run-001",
            round_no=0,
            event_type="ROUND_STARTED",
            timestamp=datetime(2026, 3, 29, 12, 1, 0, tzinfo=timezone.utc),
        )

        assert event.payload == {}


class TestInMemoryEventStore:
    def test_append_and_retrieve_events(self) -> None:
        store = InMemoryEventStore()
        event = _make_event()

        store.append(event)

        assert store.get_events("run-001") == [event]

    def test_get_events_returns_sorted_by_timestamp(self) -> None:
        store = InMemoryEventStore()
        newer = _make_event(
            event_id="evt-003",
            timestamp=datetime(2026, 3, 29, 12, 5, 0, tzinfo=timezone.utc),
        )
        older = _make_event(
            event_id="evt-002",
            timestamp=datetime(2026, 3, 29, 12, 1, 0, tzinfo=timezone.utc),
        )

        store.append(newer)
        store.append(older)

        events = store.get_events("run-001")
        assert [event.event_id for event in events] == ["evt-002", "evt-003"]

    def test_get_events_by_type_filters_correctly(self) -> None:
        store = InMemoryEventStore()
        store.append(_make_event(event_type="WORLD_INITIALIZED"))
        store.append(_make_event(event_id="evt-002", event_type="ROUND_STARTED"))
        store.append(_make_event(event_id="evt-003", event_type="ROUND_STARTED"))

        filtered = store.get_events_by_type("run-001", "ROUND_STARTED")

        assert [event.event_id for event in filtered] == ["evt-002", "evt-003"]

    def test_count_returns_number_of_events_for_run(self) -> None:
        store = InMemoryEventStore()
        store.append(_make_event())
        store.append(_make_event(event_id="evt-002"))

        assert store.count("run-001") == 2

    def test_clear_removes_all_events_for_run(self) -> None:
        store = InMemoryEventStore()
        store.append(_make_event())
        store.append(_make_event(event_id="evt-002"))

        store.clear("run-001")

        assert store.get_events("run-001") == []
        assert store.count("run-001") == 0

    def test_clear_one_run_does_not_affect_other_runs(self) -> None:
        store = InMemoryEventStore()
        store.append(_make_event(run_id="run-001"))
        store.append(_make_event(event_id="evt-002", run_id="run-002"))

        store.clear("run-001")

        assert store.get_events("run-001") == []
        assert [event.event_id for event in store.get_events("run-002")] == ["evt-002"]

    def test_empty_run_returns_empty_list(self) -> None:
        store = InMemoryEventStore()

        assert store.get_events("missing-run") == []

    def test_get_events_returns_copy_and_does_not_expose_internal_list(self) -> None:
        store = InMemoryEventStore()
        store.append(_make_event())

        events = store.get_events("run-001")
        events.clear()

        assert store.count("run-001") == 1

    def test_count_for_missing_run_is_zero(self) -> None:
        store = InMemoryEventStore()

        assert store.count("missing-run") == 0

    def test_clear_missing_run_is_noop(self) -> None:
        store = InMemoryEventStore()

        store.clear("missing-run")

        assert store.count("missing-run") == 0

    def test_get_events_by_type_for_missing_type_returns_empty(self) -> None:
        store = InMemoryEventStore()
        store.append(_make_event(event_type="WORLD_INITIALIZED"))

        assert store.get_events_by_type("run-001", "UNKNOWN") == []

    def test_thread_safety_concurrent_appends_do_not_lose_events(self) -> None:
        store = InMemoryEventStore()
        thread_count = 8
        events_per_thread = 200

        def worker(thread_id: int) -> None:
            for index in range(events_per_thread):
                store.append(
                    _make_event(
                        event_id=f"evt-{thread_id}-{index}",
                        timestamp=datetime(2026, 3, 29, 12, 0, 0, tzinfo=timezone.utc) + timedelta(seconds=index),
                    )
                )

        threads = [threading.Thread(target=worker, args=(thread_id,)) for thread_id in range(thread_count)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert store.count("run-001") == thread_count * events_per_thread
        assert len(store.get_events("run-001")) == thread_count * events_per_thread


class TestFileEventStore:
    def test_append_and_retrieve_events(self, tmp_path: Path) -> None:
        store = FileEventStore(tmp_path)
        event = _make_event()

        store.append(event)

        assert store.get_events("run-001") == [event]

    def test_constructor_creates_base_dir_if_missing(self, tmp_path: Path) -> None:
        base_dir = tmp_path / "events" / "store"

        FileEventStore(base_dir)

        assert base_dir.is_dir()

    def test_jsonl_file_contains_correct_lines(self, tmp_path: Path) -> None:
        store = FileEventStore(tmp_path)
        first = _make_event(event_id="evt-001")
        second = _make_event(event_id="evt-002", event_type="ROUND_STARTED")

        store.append(first)
        store.append(second)

        run_file = tmp_path / "run-001.jsonl"
        lines = run_file.read_text(encoding="utf-8").splitlines()
        payloads = [json.loads(line) for line in lines]

        assert len(lines) == 2
        assert payloads[0]["event_id"] == "evt-001"
        assert payloads[1]["event_id"] == "evt-002"

    def test_get_events_returns_sorted_by_timestamp(self, tmp_path: Path) -> None:
        store = FileEventStore(tmp_path)
        store.append(
            _make_event(
                event_id="evt-002",
                timestamp=datetime(2026, 3, 29, 12, 5, 0, tzinfo=timezone.utc),
            )
        )
        store.append(
            _make_event(
                event_id="evt-001",
                timestamp=datetime(2026, 3, 29, 12, 1, 0, tzinfo=timezone.utc),
            )
        )

        events = store.get_events("run-001")

        assert [event.event_id for event in events] == ["evt-001", "evt-002"]

    def test_get_events_by_type_filters_correctly(self, tmp_path: Path) -> None:
        store = FileEventStore(tmp_path)
        store.append(_make_event(event_type="WORLD_INITIALIZED"))
        store.append(_make_event(event_id="evt-002", event_type="ROUND_STARTED"))
        store.append(_make_event(event_id="evt-003", event_type="ROUND_STARTED"))

        filtered = store.get_events_by_type("run-001", "ROUND_STARTED")

        assert [event.event_id for event in filtered] == ["evt-002", "evt-003"]

    def test_count_returns_correct_number(self, tmp_path: Path) -> None:
        store = FileEventStore(tmp_path)
        store.append(_make_event(event_id="evt-001"))
        store.append(_make_event(event_id="evt-002"))
        store.append(_make_event(event_id="evt-003"))

        assert store.count("run-001") == 3

    def test_clear_removes_run_file(self, tmp_path: Path) -> None:
        store = FileEventStore(tmp_path)
        store.append(_make_event())
        run_file = tmp_path / "run-001.jsonl"

        store.clear("run-001")

        assert not run_file.exists()
        assert store.count("run-001") == 0

    def test_empty_run_returns_empty_list_and_count_zero(self, tmp_path: Path) -> None:
        store = FileEventStore(tmp_path)

        assert store.get_events("missing-run") == []
        assert store.count("missing-run") == 0

    def test_clear_missing_run_is_noop(self, tmp_path: Path) -> None:
        store = FileEventStore(tmp_path)

        store.clear("missing-run")

        assert store.count("missing-run") == 0

    def test_thread_safety_concurrent_appends(self, tmp_path: Path) -> None:
        store = FileEventStore(tmp_path)
        thread_count = 8
        events_per_thread = 100

        def worker(thread_id: int) -> None:
            for index in range(events_per_thread):
                store.append(
                    _make_event(
                        event_id=f"evt-{thread_id}-{index}",
                        timestamp=datetime(2026, 3, 29, 12, 0, 0, tzinfo=timezone.utc) + timedelta(seconds=index),
                    )
                )

        threads = [threading.Thread(target=worker, args=(thread_id,)) for thread_id in range(thread_count)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        expected = thread_count * events_per_thread
        assert store.count("run-001") == expected
        assert len(store.get_events("run-001")) == expected

    def test_separate_run_ids_use_separate_files(self, tmp_path: Path) -> None:
        store = FileEventStore(tmp_path)
        store.append(_make_event(run_id="run-a"))
        store.append(_make_event(event_id="evt-002", run_id="run-b"))

        assert (tmp_path / "run-a.jsonl").is_file()
        assert (tmp_path / "run-b.jsonl").is_file()

    def test_count_reflects_lines_in_file(self, tmp_path: Path) -> None:
        run_file = tmp_path / "run-001.jsonl"
        run_file.write_text('{"event_id":"1"}\n{"event_id":"2"}\n', encoding="utf-8")
        store = FileEventStore(tmp_path)

        assert store.count("run-001") == 2


class TestEventStoreProtocol:
    def test_inmemory_event_store_satisfies_protocol(self) -> None:
        store = InMemoryEventStore()

        assert isinstance(store, EventStore)

    def test_file_event_store_satisfies_protocol(self, tmp_path: Path) -> None:
        store = FileEventStore(tmp_path)

        assert isinstance(store, EventStore)
