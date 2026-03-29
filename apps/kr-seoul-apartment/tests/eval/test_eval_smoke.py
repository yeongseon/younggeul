from __future__ import annotations

from importlib import import_module
from typing import Any

import pytest

from .conftest import load_all_eval_cases

event_store_module = import_module("younggeul_app_kr_seoul_apartment.simulation.event_store")
graph_module = import_module("younggeul_app_kr_seoul_apartment.simulation.graph")
graph_state_module = import_module("younggeul_app_kr_seoul_apartment.simulation.graph_state")

InMemoryEventStore = event_store_module.InMemoryEventStore
build_simulation_graph = graph_module.build_simulation_graph
seed_graph_state = graph_state_module.seed_graph_state


def _run_eval_case(case: dict[str, Any]) -> tuple[Any, Any]:
    """Run a single eval case through the simulation graph. Returns (final_state, event_store)."""
    store = InMemoryEventStore()
    graph = build_simulation_graph(store)
    seed = seed_graph_state(
        user_query=case["query"],
        run_id=case["scenario_id"],
        run_name=case["run_name"],
        model_id=case["model_id"],
    )
    seed["max_rounds"] = case["max_rounds"]
    final = graph.invoke(seed)
    return final, store


@pytest.mark.eval
class TestEvalSmoke:
    def test_fixture_corpus_loads(self) -> None:
        cases = load_all_eval_cases()
        assert len(cases) >= 3
        for case in cases:
            assert "scenario_id" in case
            assert "query" in case
            assert "max_rounds" in case
            assert "expectations" in case

    def test_all_scenarios_run_without_error(self, eval_case: dict[str, Any]) -> None:
        final, store = _run_eval_case(eval_case)
        expectations = eval_case["expectations"]

        # Basic structural assertions
        assert len(final["report_claims"]) >= expectations["min_claims"]
        assert len(final["evidence_refs"]) >= expectations["min_evidence_refs"]

        # Event types
        event_types = {event.event_type for event in store.get_events(eval_case["scenario_id"])}
        for expected_type in expectations["expected_event_types"]:
            assert expected_type in event_types, f"Missing event type: {expected_type}"

    def test_all_scenarios_produce_required_claim_types(self, eval_case: dict[str, Any]) -> None:
        final, _ = _run_eval_case(eval_case)
        expectations = eval_case["expectations"]

        claim_types = {claim.claim_json.get("type") for claim in final["report_claims"]}
        for required_type in expectations["required_claim_types"]:
            assert required_type in claim_types, f"Missing claim type: {required_type}"
