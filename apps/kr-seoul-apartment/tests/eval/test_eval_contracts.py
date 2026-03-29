from __future__ import annotations

# pyright: reportMissingImports=false, reportMissingTypeStubs=false

from copy import deepcopy
from importlib import import_module
from typing import Protocol, TypedDict, cast

import pytest

event_store_module = import_module("younggeul_app_kr_seoul_apartment.simulation.event_store")
graph_module = import_module("younggeul_app_kr_seoul_apartment.simulation.graph")
graph_state_module = import_module("younggeul_app_kr_seoul_apartment.simulation.graph_state")
simulation_state_module = import_module("younggeul_core.state.simulation")
evidence_store_module = import_module("younggeul_app_kr_seoul_apartment.simulation.evidence.store")


class RunMetaLike(Protocol):
    run_id: str


class ClaimLike(Protocol):
    evidence_ids: list[str]
    claim_json: dict[str, object]


class EventLike(Protocol):
    event_type: str
    payload: dict[str, object]


class EventStoreLike(Protocol):
    def get_events(self, run_id: str) -> list[EventLike]: ...

    def get_events_by_type(self, run_id: str, event_type: str) -> list[EventLike]: ...


class EvidenceStoreLike(Protocol):
    def get(self, evidence_id: str) -> object | None: ...


class GraphLike(Protocol):
    def invoke(self, seed: dict[str, object]) -> FinalState: ...


class EventStoreFactoryLike(Protocol):
    def __call__(self) -> EventStoreLike: ...


class EvidenceStoreFactoryLike(Protocol):
    def __call__(self) -> EvidenceStoreLike: ...


class BuildSimulationGraphLike(Protocol):
    def __call__(
        self, event_store: EventStoreLike, *, evidence_store: EvidenceStoreLike | None = None
    ) -> GraphLike: ...


class SeedGraphStateLike(Protocol):
    def __call__(self, *, user_query: str, run_id: str, run_name: str, model_id: str) -> dict[str, object]: ...


class ToSimulationStateLike(Protocol):
    def __call__(self, graph_state: FinalState) -> dict[str, object]: ...


class FinalState(TypedDict):
    run_meta: RunMetaLike
    snapshot: object
    scenario: object
    round_no: int
    max_rounds: int
    world: dict[str, object]
    participants: dict[str, object]
    governance_actions: dict[str, object]
    market_actions: dict[str, object]
    event_refs: list[str]
    evidence_refs: list[str]
    report_claims: list[ClaimLike]
    warnings: list[str]


InMemoryEventStore = cast(EventStoreFactoryLike, event_store_module.InMemoryEventStore)
build_simulation_graph = cast(BuildSimulationGraphLike, graph_module.build_simulation_graph)
seed_graph_state = cast(SeedGraphStateLike, graph_state_module.seed_graph_state)
to_simulation_state = cast(ToSimulationStateLike, graph_state_module.to_simulation_state)
InMemoryEvidenceStore = cast(EvidenceStoreFactoryLike, evidence_store_module.InMemoryEvidenceStore)


def _run_with_stores(
    case: dict[str, object],
) -> tuple[FinalState, EventStoreLike, EvidenceStoreLike]:
    event_store = InMemoryEventStore()
    evidence_store = InMemoryEvidenceStore()
    graph = build_simulation_graph(event_store, evidence_store=evidence_store)
    seed = seed_graph_state(
        user_query=cast(str, case["query"]),
        run_id=cast(str, case["scenario_id"]),
        run_name=cast(str, case["run_name"]),
        model_id=cast(str, case["model_id"]),
    )
    seed["max_rounds"] = cast(int, case["max_rounds"])
    final = graph.invoke(seed)
    return final, event_store, evidence_store


def _event_index(events: list[EventLike], event_type: str) -> int:
    for idx, event in enumerate(events):
        if event.event_type == event_type:
            return idx
    raise AssertionError(f"Missing event type: {event_type}")


@pytest.mark.eval
class TestEvalContracts:
    def test_final_state_has_all_required_keys(self, eval_case: dict[str, object]) -> None:
        final, _, _ = _run_with_stores(eval_case)
        required_keys = {
            "run_meta",
            "snapshot",
            "scenario",
            "round_no",
            "max_rounds",
            "world",
            "participants",
            "governance_actions",
            "market_actions",
            "event_refs",
            "evidence_refs",
            "report_claims",
            "warnings",
        }

        assert required_keys.issubset(set(final.keys()))

    def test_final_state_converts_to_simulation_state(self, eval_case: dict[str, object]) -> None:
        final, _, _ = _run_with_stores(eval_case)

        converted = to_simulation_state(final)

        assert converted["run_meta"] is not None
        assert converted["scenario"] is not None
        assert converted["round_no"] is not None
        assert converted["max_rounds"] is not None

    def test_evidence_claim_referential_integrity(self, eval_case: dict[str, object]) -> None:
        final, _, evidence_store = _run_with_stores(eval_case)

        for claim in final["report_claims"]:
            for evidence_id in claim.evidence_ids:
                assert evidence_store.get(evidence_id) is not None

    def test_citation_gate_payload_matches_claim_count(self, eval_case: dict[str, object]) -> None:
        final, event_store, _ = _run_with_stores(eval_case)
        run_id = final["run_meta"].run_id

        citation_gate_events = event_store.get_events_by_type(run_id, "CITATION_GATE")
        assert citation_gate_events, "Missing CITATION_GATE event"
        payload = citation_gate_events[-1].payload
        total_claims = cast(int, payload["total_claims"])
        passed = cast(int, payload["passed"])
        failed = cast(int, payload["failed"])

        assert total_claims == len(final["report_claims"])
        assert passed + failed == total_claims

    def test_same_input_same_output_determinism(self, eval_case: dict[str, object]) -> None:
        base_scenario_id = cast(str, eval_case["scenario_id"])
        base_run_name = cast(str, eval_case["run_name"])

        case_a = deepcopy(eval_case)
        case_a["scenario_id"] = f"{base_scenario_id}-determinism-a"
        case_a["run_name"] = f"{base_run_name}-determinism-a"

        case_b = deepcopy(eval_case)
        case_b["scenario_id"] = f"{base_scenario_id}-determinism-b"
        case_b["run_name"] = f"{base_run_name}-determinism-b"

        final_a, _, _ = _run_with_stores(case_a)
        final_b, _, _ = _run_with_stores(case_b)

        claim_types_a = {claim.claim_json.get("type") for claim in final_a["report_claims"]}
        claim_types_b = {claim.claim_json.get("type") for claim in final_b["report_claims"]}

        assert len(final_a["report_claims"]) == len(final_b["report_claims"])
        assert claim_types_a == claim_types_b
        assert len(final_a["evidence_refs"]) == len(final_b["evidence_refs"])
        assert final_a["max_rounds"] == final_b["max_rounds"]
        assert final_a["round_no"] == final_b["round_no"]

    def test_event_sequence_invariant(self, eval_case: dict[str, object]) -> None:
        final, event_store, _ = _run_with_stores(eval_case)
        run_id = final["run_meta"].run_id
        events = event_store.get_events(run_id)

        intake_idx = _event_index(events, "INTAKE_PLANNED")
        scenario_idx = _event_index(events, "SCENARIO_BUILT")
        world_idx = _event_index(events, "WORLD_INITIALIZED")
        simulation_completed_idx = _event_index(events, "SIMULATION_COMPLETED")
        report_written_idx = _event_index(events, "REPORT_WRITTEN")
        critic_idx = _event_index(events, "CRITIC")
        citation_gate_idx = _event_index(events, "CITATION_GATE")
        report_rendered_idx = _event_index(events, "REPORT_RENDERED")

        assert intake_idx < scenario_idx
        assert scenario_idx < world_idx
        assert simulation_completed_idx < report_written_idx
        assert report_written_idx < critic_idx
        assert critic_idx < citation_gate_idx
        assert citation_gate_idx < report_rendered_idx

    def test_evidence_records_have_valid_structure(self, eval_case: dict[str, object]) -> None:
        final, _, evidence_store = _run_with_stores(eval_case)

        required_fields = [
            "evidence_id",
            "kind",
            "subject_type",
            "subject_id",
            "round_no",
            "payload",
            "created_at",
        ]
        for evidence_id in final["evidence_refs"]:
            record = evidence_store.get(evidence_id)
            assert record is not None
            for field_name in required_fields:
                assert hasattr(record, field_name)
                assert getattr(record, field_name) is not None

    def test_report_claims_evidence_ids_are_subset_of_evidence_refs(
        self,
        eval_case: dict[str, object],
    ) -> None:
        final, _, _ = _run_with_stores(eval_case)

        evidence_refs = set(final["evidence_refs"])
        claim_evidence_ids = {evidence_id for claim in final["report_claims"] for evidence_id in claim.evidence_ids}

        assert claim_evidence_ids.issubset(evidence_refs)
