from importlib import import_module
from typing import Any

event_store_module = import_module("younggeul_app_kr_seoul_apartment.simulation.event_store")
graph_module = import_module("younggeul_app_kr_seoul_apartment.simulation.graph")
graph_state_module = import_module("younggeul_app_kr_seoul_apartment.simulation.graph_state")
simulation_state_module = import_module("younggeul_core.state.simulation")
report_schema_module = import_module("younggeul_app_kr_seoul_apartment.simulation.schemas.report")

InMemoryEventStore = event_store_module.InMemoryEventStore
build_simulation_graph = graph_module.build_simulation_graph
seed_graph_state = graph_state_module.seed_graph_state
ReportClaim = simulation_state_module.ReportClaim
RenderedReport = report_schema_module.RenderedReport
RenderedSection = report_schema_module.RenderedSection
RenderedClaimEntry = report_schema_module.RenderedClaimEntry


def _make_seed(run_id: str, *, max_rounds: int = 2) -> dict[str, Any]:
    state = seed_graph_state(
        user_query="강남구 아파트 시장 시뮬레이션",
        run_id=run_id,
        run_name=f"run-{run_id}",
        model_id="gpt-test",
    )
    state["max_rounds"] = max_rounds
    return state


def _run_graph(run_id: str, *, max_rounds: int = 2) -> tuple[InMemoryEventStore, dict[str, Any]]:
    store = InMemoryEventStore()
    graph = build_simulation_graph(store)
    final = graph.invoke(_make_seed(run_id, max_rounds=max_rounds))
    return store, final


def _single_event_payload(store: InMemoryEventStore, run_id: str, event_type: str) -> dict[str, Any]:
    events = store.get_events_by_type(run_id, event_type)
    assert len(events) == 1
    return events[0].payload


def _rendered_report_from_event(store: InMemoryEventStore, run_id: str) -> RenderedReport:
    payload = _single_event_payload(store, run_id, "REPORT_RENDERED")
    return RenderedReport.model_validate(payload["rendered_report"])


def _event_index(event_types: list[str], target: str) -> int:
    return event_types.index(target)


class TestReportPipelineE2E:
    def test_full_pipeline_produces_evidence_and_report(self) -> None:
        run_id = "run-full-pipeline"
        store, final = _run_graph(run_id, max_rounds=2)

        evidence_refs = final["evidence_refs"]
        assert isinstance(evidence_refs, list)
        assert evidence_refs
        assert all(isinstance(reference, str) and bool(reference) for reference in evidence_refs)

        report_claims = final["report_claims"]
        assert len(report_claims) >= 5
        assert all(isinstance(claim, ReportClaim) for claim in report_claims)
        assert {claim.gate_status for claim in report_claims} == {"pending"}

        assert store.get_events_by_type(run_id, "EVIDENCE_BUILT") == []
        assert len(store.get_events_by_type(run_id, "REPORT_WRITTEN")) == 1
        assert len(store.get_events_by_type(run_id, "CITATION_GATE")) == 1
        assert len(store.get_events_by_type(run_id, "REPORT_RENDERED")) == 1

    def test_citation_gate_validates_all_claims(self) -> None:
        run_id = "run-citation-gate"
        store, final = _run_graph(run_id, max_rounds=2)

        payload = _single_event_payload(store, run_id, "CITATION_GATE")
        total_claims = len(final["report_claims"])

        assert payload["total_claims"] == total_claims
        assert payload["passed"] == total_claims
        assert payload["failed"] == 0
        assert payload["failed_claim_ids"] == []

    def test_report_renderer_produces_valid_rendered_report(self) -> None:
        run_id = "run-rendered-report"
        store, _ = _run_graph(run_id, max_rounds=2)

        rendered = _rendered_report_from_event(store, run_id)

        assert rendered.total_claims > 0
        assert rendered.passed_claims > 0
        assert rendered.failed_claims == 0
        assert rendered.sections
        assert "# Simulation Report" in rendered.markdown
        assert run_id in rendered.markdown
        assert "**Round**:" in rendered.markdown

    def test_report_sections_cover_expected_claim_types(self) -> None:
        run_id = "run-report-sections"
        store, _ = _run_graph(run_id, max_rounds=2)

        rendered = _rendered_report_from_event(store, run_id)
        section_keys = {section.section_key for section in rendered.sections}

        assert section_keys.intersection({"summary", "direction", "volume", "drivers", "risks"})
        for section in rendered.sections:
            assert isinstance(section, RenderedSection)
            assert section.claims
            for claim_entry in section.claims:
                assert isinstance(claim_entry, RenderedClaimEntry)
                assert claim_entry.statement

    def test_evidence_refs_are_unique_and_non_empty(self) -> None:
        _, final = _run_graph("run-evidence-refs-unique", max_rounds=2)

        evidence_refs = final["evidence_refs"]
        assert evidence_refs
        assert all(isinstance(reference, str) and bool(reference) for reference in evidence_refs)
        assert len(evidence_refs) == len(set(evidence_refs))

    def test_report_claims_have_structured_claim_json(self) -> None:
        _, final = _run_graph("run-claim-json", max_rounds=2)

        report_claims = final["report_claims"]
        assert report_claims
        for claim in report_claims:
            claim_json = claim.claim_json
            assert "type" in claim_json
            assert "statement" in claim_json or "summary" in claim_json
            assert isinstance(claim_json["type"], str)

    def test_zero_round_pipeline_still_produces_report(self) -> None:
        run_id = "run-zero-round-pipeline"
        store, final = _run_graph(run_id, max_rounds=0)

        assert len(final["report_claims"]) >= 5
        assert len(store.get_events_by_type(run_id, "REPORT_RENDERED")) == 1

        rendered = _rendered_report_from_event(store, run_id)
        assert rendered.sections

    def test_pipeline_determinism_same_structure(self) -> None:
        run_id = "run-determinism"
        store_a, final_a = _run_graph(run_id, max_rounds=2)
        store_b, final_b = _run_graph(run_id, max_rounds=2)

        claim_types_a = [str(claim.claim_json["type"]) for claim in final_a["report_claims"]]
        claim_types_b = [str(claim.claim_json["type"]) for claim in final_b["report_claims"]]

        rendered_a = _rendered_report_from_event(store_a, run_id)
        rendered_b = _rendered_report_from_event(store_b, run_id)

        section_keys_a = [section.section_key for section in rendered_a.sections]
        section_keys_b = [section.section_key for section in rendered_b.sections]

        assert len(final_a["report_claims"]) == len(final_b["report_claims"])
        assert claim_types_a == claim_types_b
        assert section_keys_a == section_keys_b
        assert len(final_a["evidence_refs"]) == len(final_b["evidence_refs"])

    def test_event_ordering_follows_pipeline_sequence(self) -> None:
        run_id = "run-event-order"
        store, _ = _run_graph(run_id, max_rounds=1)
        event_types = [event.event_type for event in store.get_events(run_id)]

        assert _event_index(event_types, "INTAKE_PLANNED") < _event_index(event_types, "SCENARIO_BUILT")
        assert _event_index(event_types, "SCENARIO_BUILT") < _event_index(event_types, "WORLD_INITIALIZED")
        assert _event_index(event_types, "ROUND_RESOLVED") < _event_index(event_types, "SIMULATION_COMPLETED")
        assert _event_index(event_types, "SIMULATION_COMPLETED") < _event_index(event_types, "REPORT_WRITTEN")
        assert _event_index(event_types, "REPORT_WRITTEN") < _event_index(event_types, "CRITIC")
        assert _event_index(event_types, "CRITIC") < _event_index(event_types, "CITATION_GATE")
        assert _event_index(event_types, "CITATION_GATE") < _event_index(event_types, "REPORT_RENDERED")

    def test_markdown_includes_all_passed_claim_statements(self) -> None:
        run_id = "run-markdown-coverage"
        store, _ = _run_graph(run_id, max_rounds=2)

        rendered = _rendered_report_from_event(store, run_id)
        markdown = rendered.markdown

        for section in rendered.sections:
            for claim_entry in section.claims:
                assert claim_entry.statement in markdown
