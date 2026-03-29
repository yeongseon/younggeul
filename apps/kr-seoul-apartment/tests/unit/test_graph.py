from datetime import timezone
from importlib import import_module

import pytest
from langgraph.graph.state import CompiledStateGraph

event_store_module = import_module("younggeul_app_kr_seoul_apartment.simulation.event_store")
graph_module = import_module("younggeul_app_kr_seoul_apartment.simulation.graph")
graph_state_module = import_module("younggeul_app_kr_seoul_apartment.simulation.graph_state")
simulation_state_module = import_module("younggeul_core.state.simulation")

InMemoryEventStore = event_store_module.InMemoryEventStore
DEFAULT_MAX_ROUNDS = graph_module.DEFAULT_MAX_ROUNDS
build_simulation_graph = graph_module.build_simulation_graph
SimulationGraphState = graph_state_module.SimulationGraphState
seed_graph_state = graph_state_module.seed_graph_state
to_simulation_state = graph_state_module.to_simulation_state
RoundOutcome = simulation_state_module.RoundOutcome
ScenarioSpec = simulation_state_module.ScenarioSpec
SnapshotRef = simulation_state_module.SnapshotRef


def _make_seed(run_id: str, *, max_rounds: int | None = None) -> SimulationGraphState:
    state = seed_graph_state(
        user_query="강남구 아파트 시장 시뮬레이션",
        run_id=run_id,
        run_name=f"run-{run_id}",
        model_id="gpt-test",
    )
    if max_rounds is not None:
        state["max_rounds"] = max_rounds
    return state


def test_build_simulation_graph_compiles() -> None:
    store = InMemoryEventStore()

    graph = build_simulation_graph(store)

    assert isinstance(graph, CompiledStateGraph)


def test_graph_runs_end_to_end() -> None:
    store = InMemoryEventStore()
    graph = build_simulation_graph(store)

    final = graph.invoke(_make_seed("run-end-to-end", max_rounds=2))

    assert final["intake_plan"]["planner_status"] == "stub"
    assert isinstance(final["scenario"], ScenarioSpec)
    assert final["round_no"] == 2
    assert len(final["report_claims"]) == 1

    simulation_state = to_simulation_state(final)
    assert simulation_state["max_rounds"] == 2
    assert simulation_state["round_no"] == 2


@pytest.mark.parametrize("max_rounds", [0, 1, 3, 5])
def test_round_loop_executes_exactly_n_rounds(max_rounds: int) -> None:
    store = InMemoryEventStore()
    graph = build_simulation_graph(store)
    run_id = f"run-rounds-{max_rounds}"

    final = graph.invoke(_make_seed(run_id, max_rounds=max_rounds))

    decisions_events = store.get_events_by_type(run_id, "DECISIONS_MADE")
    resolved_events = store.get_events_by_type(run_id, "ROUND_RESOLVED")
    assert len(decisions_events) == max_rounds
    assert len(resolved_events) == max_rounds
    assert final["round_no"] == max_rounds


def test_round_loop_zero_rounds_skips_to_report() -> None:
    store = InMemoryEventStore()
    graph = build_simulation_graph(store)

    final = graph.invoke(_make_seed("run-zero", max_rounds=0))

    assert final["round_no"] == 0
    assert store.get_events_by_type("run-zero", "DECISIONS_MADE") == []
    assert store.get_events_by_type("run-zero", "ROUND_RESOLVED") == []


def test_stubs_emit_events_to_store() -> None:
    max_rounds = 4
    store = InMemoryEventStore()
    graph = build_simulation_graph(store)

    graph.invoke(_make_seed("run-event-count", max_rounds=max_rounds))

    assert store.count("run-event-count") == 7 + (2 * max_rounds)


def test_event_types_emitted() -> None:
    store = InMemoryEventStore()
    graph = build_simulation_graph(store)
    run_id = "run-event-types"

    graph.invoke(_make_seed(run_id, max_rounds=2))

    event_types = {event.event_type for event in store.get_events(run_id)}
    assert event_types == {
        "INTAKE_PLANNED",
        "SCENARIO_BUILT",
        "WORLD_INITIALIZED",
        "DECISIONS_MADE",
        "ROUND_RESOLVED",
        "SIMULATION_COMPLETED",
        "REPORT_WRITTEN",
        "CRITIC",
        "CITATION_GATE",
    }


def test_intake_planner_stub_sets_intake_plan() -> None:
    store = InMemoryEventStore()
    graph = build_simulation_graph(store)

    final = graph.invoke(_make_seed("run-intake", max_rounds=0))

    assert final["intake_plan"]["query"] == "강남구 아파트 시장 시뮬레이션"
    assert final["intake_plan"]["planner_status"] == "stub"


def test_scenario_builder_stub_sets_scenario() -> None:
    store = InMemoryEventStore()
    graph = build_simulation_graph(store)

    final = graph.invoke(_make_seed("run-scenario", max_rounds=0))
    scenario = final["scenario"]

    assert scenario.scenario_name == "Stub Scenario"
    assert scenario.target_gus == ["11680"]
    assert scenario.target_period_start.isoformat() == "2026-01-01"
    assert scenario.target_period_end.isoformat() == "2026-12-31"


def test_world_initializer_stub_sets_world_and_participants() -> None:
    store = InMemoryEventStore()
    graph = build_simulation_graph(store)

    final = graph.invoke(_make_seed("run-world", max_rounds=0))

    assert "11680" in final["world"]
    assert final["world"]["11680"].gu_name == "강남구"
    assert "p-001" in final["participants"]
    assert final["participants"]["p-001"].role == "buyer"
    assert "p-002" in final["participants"]
    assert final["participants"]["p-002"].role == "investor"


def test_round_loop_sets_round_no_after_n_rounds() -> None:
    store = InMemoryEventStore()
    graph = build_simulation_graph(store)
    run_id = "run-increment"

    final = graph.invoke(_make_seed(run_id, max_rounds=3))

    resolved_events = store.get_events_by_type(run_id, "ROUND_RESOLVED")
    assert [event.round_no for event in resolved_events] == [1, 2, 3]
    assert final["round_no"] == 3


def test_round_loop_sets_last_outcome() -> None:
    store = InMemoryEventStore()
    graph = build_simulation_graph(store)

    final = graph.invoke(_make_seed("run-outcome", max_rounds=1))

    assert isinstance(final["last_outcome"], RoundOutcome)
    assert final["last_outcome"].round_no == 1


def test_report_writer_stub_appends_claim() -> None:
    store = InMemoryEventStore()
    graph = build_simulation_graph(store)

    final = graph.invoke(_make_seed("run-report", max_rounds=0))

    assert len(final["report_claims"]) == 1
    claim = final["report_claims"][0]
    assert claim.claim_json == {"summary": "stub report"}
    assert claim.gate_status == "passed"


def test_passthrough_stubs_only_add_event_refs() -> None:
    store = InMemoryEventStore()
    graph = build_simulation_graph(store)
    run_id = "run-passthrough"

    final = graph.invoke(_make_seed(run_id, max_rounds=0))

    assert final["warnings"] == []
    assert final["evidence_refs"] == []
    assert len(final["report_claims"]) == 1
    critic_events = store.get_events_by_type(run_id, "CRITIC")
    citation_events = store.get_events_by_type(run_id, "CITATION_GATE")
    assert len(critic_events) == 1
    assert len(citation_events) == 1
    assert critic_events[0].payload == {}
    assert citation_events[0].payload == {}


def test_final_state_convertible_to_simulation_state() -> None:
    store = InMemoryEventStore()
    graph = build_simulation_graph(store)

    final = graph.invoke(_make_seed("run-convert", max_rounds=2))
    converted = to_simulation_state(final)

    assert converted["round_no"] == 2
    assert converted["scenario"].scenario_name == "Stub Scenario"


def test_mermaid_smoke() -> None:
    store = InMemoryEventStore()
    graph = build_simulation_graph(store)

    mermaid = graph.get_graph().draw_mermaid()

    assert "intake_planner" in mermaid
    assert "scenario_builder" in mermaid
    assert "world_initializer" in mermaid
    assert "participant_decider" in mermaid
    assert "round_resolver" in mermaid
    assert "round_summarizer" in mermaid
    assert "report_writer" in mermaid
    assert "critic" in mermaid
    assert "citation_gate" in mermaid


def test_default_max_rounds_used_when_not_in_state() -> None:
    store = InMemoryEventStore()
    graph = build_simulation_graph(store)

    final = graph.invoke(_make_seed("run-default"))

    assert final["max_rounds"] == DEFAULT_MAX_ROUNDS
    assert final["round_no"] == DEFAULT_MAX_ROUNDS


def test_custom_max_rounds_override() -> None:
    store = InMemoryEventStore()
    graph = build_simulation_graph(store, default_max_rounds=9)

    final = graph.invoke(_make_seed("run-custom", max_rounds=2))

    assert final["max_rounds"] == 2
    assert final["round_no"] == 2


def test_event_refs_are_unique_strings() -> None:
    store = InMemoryEventStore()
    graph = build_simulation_graph(store)

    final = graph.invoke(_make_seed("run-event-refs", max_rounds=3))
    refs = final["event_refs"]

    assert all(isinstance(reference, str) for reference in refs)
    assert len(set(refs)) == len(refs)


def test_multiple_runs_with_same_graph_independent() -> None:
    store = InMemoryEventStore()
    graph = build_simulation_graph(store)

    final_a = graph.invoke(_make_seed("run-a", max_rounds=1))
    final_b = graph.invoke(_make_seed("run-b", max_rounds=3))

    assert store.count("run-a") == 9
    assert store.count("run-b") == 13
    assert final_a["round_no"] == 1
    assert final_b["round_no"] == 3
    assert set(final_a["event_refs"]).isdisjoint(set(final_b["event_refs"]))


def test_world_initializer_stub_uses_existing_snapshot_when_present() -> None:
    store = InMemoryEventStore()
    graph = build_simulation_graph(store)
    seed = _make_seed("run-existing-snapshot", max_rounds=0)
    seed["snapshot"] = SnapshotRef(
        dataset_snapshot_id="0" * 64,
        created_at=seed["run_meta"].created_at,
        table_count=99,
    )

    final = graph.invoke(seed)

    assert final["snapshot"].table_count == 99


def test_event_timestamps_are_timezone_aware() -> None:
    store = InMemoryEventStore()
    graph = build_simulation_graph(store)
    run_id = "run-timezone"

    graph.invoke(_make_seed(run_id, max_rounds=0))

    assert all(event.timestamp.tzinfo is not None for event in store.get_events(run_id))
    assert all(event.timestamp.tzinfo == timezone.utc for event in store.get_events(run_id))
