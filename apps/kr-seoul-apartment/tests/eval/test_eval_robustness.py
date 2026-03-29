from __future__ import annotations

from datetime import datetime, timezone
from importlib import import_module
from typing import Protocol, cast

import pytest

event_store_module = import_module("younggeul_app_kr_seoul_apartment.simulation.event_store")
graph_module = import_module("younggeul_app_kr_seoul_apartment.simulation.graph")
graph_state_module = import_module("younggeul_app_kr_seoul_apartment.simulation.graph_state")
evidence_store_module = import_module("younggeul_app_kr_seoul_apartment.simulation.evidence.store")


class RunMetaLike(Protocol):
    run_id: str


class ClaimLike(Protocol):
    evidence_ids: list[str]


class EventLike(Protocol):
    run_id: str
    event_type: str


class EventStoreLike(Protocol):
    def get_events(self, run_id: str) -> list[EventLike]: ...

    def get_events_by_type(self, run_id: str, event_type: str) -> list[EventLike]: ...


class EvidenceRecordLike(Protocol):
    evidence_id: str


class EvidenceStoreLike(Protocol):
    def add(self, record: EvidenceRecordLike) -> None: ...

    def get(self, evidence_id: str) -> EvidenceRecordLike | None: ...

    def count(self) -> int: ...


class GraphLike(Protocol):
    def invoke(self, seed: dict[str, object], config: dict[str, object] | None = None) -> FinalState: ...


class EventStoreFactoryLike(Protocol):
    def __call__(self) -> EventStoreLike: ...


class EvidenceStoreFactoryLike(Protocol):
    def __call__(self) -> EvidenceStoreLike: ...


class EvidenceRecordFactoryLike(Protocol):
    def __call__(
        self,
        *,
        evidence_id: str,
        kind: str,
        subject_type: str,
        subject_id: str,
        round_no: int,
        payload: dict[str, object],
        created_at: datetime,
        source_event_ids: list[str] | None = None,
    ) -> EvidenceRecordLike: ...


class BuildSimulationGraphLike(Protocol):
    def __call__(
        self,
        event_store: EventStoreLike,
        *,
        evidence_store: EvidenceStoreLike | None = None,
    ) -> GraphLike: ...


class SeedGraphStateLike(Protocol):
    def __call__(
        self,
        *,
        user_query: str,
        run_id: str,
        run_name: str,
        model_id: str,
    ) -> dict[str, object]: ...


class FinalState(Protocol):
    run_meta: RunMetaLike

    def __getitem__(self, key: str) -> object: ...

    def keys(self) -> list[str]: ...


InMemoryEventStore = cast(EventStoreFactoryLike, event_store_module.InMemoryEventStore)
build_simulation_graph = cast(BuildSimulationGraphLike, graph_module.build_simulation_graph)
seed_graph_state = cast(SeedGraphStateLike, graph_state_module.seed_graph_state)
InMemoryEvidenceStore = cast(EvidenceStoreFactoryLike, evidence_store_module.InMemoryEvidenceStore)
EvidenceRecord = cast(EvidenceRecordFactoryLike, evidence_store_module.EvidenceRecord)


def _run(
    *,
    run_id: str,
    run_name: str,
    user_query: str,
    max_rounds: int | None,
    event_store: EventStoreLike,
    evidence_store: EvidenceStoreLike,
) -> tuple[FinalState, EventStoreLike, EvidenceStoreLike]:
    graph = build_simulation_graph(event_store, evidence_store=evidence_store)
    seed = seed_graph_state(
        user_query=user_query,
        run_id=run_id,
        run_name=run_name,
        model_id="gpt-4o-mini",
    )
    if max_rounds is not None:
        seed["max_rounds"] = max_rounds
    final = graph.invoke(seed, {"recursion_limit": 100})
    return final, event_store, evidence_store


@pytest.mark.eval
class TestEvalRobustness:
    def test_large_round_count_ten_rounds_completes(self) -> None:
        store = InMemoryEventStore()
        evidence_store = InMemoryEvidenceStore()
        final, event_store, _ = _run(
            run_id="robust-large-rounds-10",
            run_name="robust-large-rounds-10",
            user_query="Run a 10-round stress simulation for Gangnam apartment market.",
            max_rounds=10,
            event_store=store,
            evidence_store=evidence_store,
        )

        run_id = cast(RunMetaLike, final["run_meta"]).run_id
        events = event_store.get_events(run_id)
        assert len(events) == 28
        assert evidence_store.count() > 0
        assert len(cast(list[ClaimLike], final["report_claims"])) > 0

    def test_zero_round_scenario_completes_with_report(self) -> None:
        store = InMemoryEventStore()
        evidence_store = InMemoryEvidenceStore()
        final, event_store, _ = _run(
            run_id="robust-zero-rounds",
            run_name="robust-zero-rounds",
            user_query="Zero-round smoke path.",
            max_rounds=0,
            event_store=store,
            evidence_store=evidence_store,
        )

        run_id = cast(RunMetaLike, final["run_meta"]).run_id
        assert len(event_store.get_events_by_type(run_id, "DECISIONS_MADE")) == 0
        assert len(event_store.get_events_by_type(run_id, "ROUND_RESOLVED")) == 0
        assert len(cast(list[ClaimLike], final["report_claims"])) > 0

    def test_single_round_event_counts_are_exact(self) -> None:
        store = InMemoryEventStore()
        evidence_store = InMemoryEvidenceStore()
        final, event_store, _ = _run(
            run_id="robust-single-round",
            run_name="robust-single-round",
            user_query="Single-round boundary scenario.",
            max_rounds=1,
            event_store=store,
            evidence_store=evidence_store,
        )

        run_id = cast(RunMetaLike, final["run_meta"]).run_id
        assert len(event_store.get_events_by_type(run_id, "DECISIONS_MADE")) == 1
        assert len(event_store.get_events_by_type(run_id, "ROUND_RESOLVED")) == 1
        assert len(event_store.get_events(run_id)) == 10

    def test_default_max_rounds_is_used_when_missing_on_seed(self) -> None:
        store = InMemoryEventStore()
        evidence_store = InMemoryEvidenceStore()
        final, _, _ = _run(
            run_id="robust-default-rounds",
            run_name="robust-default-rounds",
            user_query="Use default max rounds.",
            max_rounds=None,
            event_store=store,
            evidence_store=evidence_store,
        )

        assert cast(int, final["max_rounds"]) == 3
        assert cast(int, final["round_no"]) == 3

    def test_very_long_user_query_is_preserved_and_completes(self) -> None:
        long_query = "서울 아파트 시장 분석 " + ("매우긴질문-" * 1800)
        assert len(long_query) > 10000

        store = InMemoryEventStore()
        evidence_store = InMemoryEvidenceStore()
        final, _, _ = _run(
            run_id="robust-long-query",
            run_name="robust-long-query",
            user_query=long_query,
            max_rounds=2,
            event_store=store,
            evidence_store=evidence_store,
        )

        intake_plan = cast(dict[str, object], final["intake_plan"])
        assert cast(str, intake_plan["query"]) == long_query
        assert len(cast(list[ClaimLike], final["report_claims"])) > 0

    def test_report_claims_never_have_empty_evidence_ids(self) -> None:
        store = InMemoryEventStore()
        evidence_store = InMemoryEvidenceStore()
        final, _, _ = _run(
            run_id="robust-non-empty-claim-evidence",
            run_name="robust-non-empty-claim-evidence",
            user_query="Validate claim evidence links.",
            max_rounds=3,
            event_store=store,
            evidence_store=evidence_store,
        )

        for claim in cast(list[ClaimLike], final["report_claims"]):
            assert len(claim.evidence_ids) > 0

    def test_event_isolation_between_runs_on_shared_event_store(self) -> None:
        shared_event_store = InMemoryEventStore()
        evidence_store_a = InMemoryEvidenceStore()
        evidence_store_b = InMemoryEvidenceStore()

        final_a, event_store, _ = _run(
            run_id="robust-event-isolation-a",
            run_name="robust-event-isolation-a",
            user_query="Run A for event isolation.",
            max_rounds=2,
            event_store=shared_event_store,
            evidence_store=evidence_store_a,
        )
        final_b, _, _ = _run(
            run_id="robust-event-isolation-b",
            run_name="robust-event-isolation-b",
            user_query="Run B for event isolation.",
            max_rounds=4,
            event_store=shared_event_store,
            evidence_store=evidence_store_b,
        )

        run_id_a = cast(RunMetaLike, final_a["run_meta"]).run_id
        run_id_b = cast(RunMetaLike, final_b["run_meta"]).run_id
        events_a = event_store.get_events(run_id_a)
        events_b = event_store.get_events(run_id_b)
        assert events_a
        assert events_b
        assert all(event.run_id == run_id_a for event in events_a)
        assert all(event.run_id == run_id_b for event in events_b)

    def test_evidence_isolation_between_runs_on_separate_evidence_stores(self) -> None:
        shared_event_store = InMemoryEventStore()
        evidence_store_a = InMemoryEvidenceStore()
        evidence_store_b = InMemoryEvidenceStore()

        final_a, _, _ = _run(
            run_id="robust-evidence-isolation-a",
            run_name="robust-evidence-isolation-a",
            user_query="Run A for evidence isolation.",
            max_rounds=2,
            event_store=shared_event_store,
            evidence_store=evidence_store_a,
        )
        final_b, _, _ = _run(
            run_id="robust-evidence-isolation-b",
            run_name="robust-evidence-isolation-b",
            user_query="Run B for evidence isolation.",
            max_rounds=2,
            event_store=shared_event_store,
            evidence_store=evidence_store_b,
        )

        for evidence_id in cast(list[str], final_a["evidence_refs"]):
            assert evidence_store_a.get(evidence_id) is not None
            assert evidence_store_b.get(evidence_id) is None

        for evidence_id in cast(list[str], final_b["evidence_refs"]):
            assert evidence_store_b.get(evidence_id) is not None
            assert evidence_store_a.get(evidence_id) is None

    def test_duplicate_evidence_id_raises_value_error(self) -> None:
        evidence_store = InMemoryEvidenceStore()
        now = datetime.now(timezone.utc)
        record = EvidenceRecord(
            evidence_id="duplicate-evidence-id",
            kind="simulation_fact",
            subject_type="simulation",
            subject_id="run-x",
            round_no=0,
            payload={"x": 1},
            source_event_ids=[],
            created_at=now,
        )
        evidence_store.add(record)

        with pytest.raises(ValueError):
            evidence_store.add(record)

    def test_graph_produces_complete_state_even_at_zero_rounds(self) -> None:
        store = InMemoryEventStore()
        evidence_store = InMemoryEvidenceStore()
        final, _, _ = _run(
            run_id="robust-complete-state-zero-rounds",
            run_name="robust-complete-state-zero-rounds",
            user_query="Validate complete state keys at zero rounds.",
            max_rounds=0,
            event_store=store,
            evidence_store=evidence_store,
        )

        required = {
            "run_meta",
            "snapshot",
            "scenario",
            "round_no",
            "max_rounds",
            "world",
            "participants",
            "event_refs",
            "evidence_refs",
            "report_claims",
            "warnings",
        }
        assert required.issubset(set(final.keys()))

    def test_evidence_refs_match_evidence_store_contents(self) -> None:
        store = InMemoryEventStore()
        evidence_store = InMemoryEvidenceStore()
        final, _, _ = _run(
            run_id="robust-evidence-ref-integrity",
            run_name="robust-evidence-ref-integrity",
            user_query="Ensure no orphan evidence refs.",
            max_rounds=3,
            event_store=store,
            evidence_store=evidence_store,
        )

        for evidence_id in cast(list[str], final["evidence_refs"]):
            assert evidence_store.get(evidence_id) is not None

    def test_round_no_matches_max_rounds_after_completion(self) -> None:
        store = InMemoryEventStore()
        evidence_store = InMemoryEvidenceStore()
        final, _, _ = _run(
            run_id="robust-round-no-matches-max-rounds",
            run_name="robust-round-no-matches-max-rounds",
            user_query="Round count consistency check.",
            max_rounds=5,
            event_store=store,
            evidence_store=evidence_store,
        )

        assert cast(int, final["round_no"]) == cast(int, final["max_rounds"])
