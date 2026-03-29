from __future__ import annotations

import json
from importlib import import_module
from types import SimpleNamespace
from typing import Any, TypeVar
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel, ValidationError

event_store_module = import_module("younggeul_app_kr_seoul_apartment.simulation.event_store")
graph_module = import_module("younggeul_app_kr_seoul_apartment.simulation.graph")
graph_state_module = import_module("younggeul_app_kr_seoul_apartment.simulation.graph_state")
litellm_adapter_module = import_module("younggeul_app_kr_seoul_apartment.simulation.llm.litellm_adapter")
llm_ports_module = import_module("younggeul_app_kr_seoul_apartment.simulation.llm.ports")
intake_node_module = import_module("younggeul_app_kr_seoul_apartment.simulation.nodes.intake_planner")
intake_schema_module = import_module("younggeul_app_kr_seoul_apartment.simulation.schemas.intake")

InMemoryEventStore = event_store_module.InMemoryEventStore
build_simulation_graph = graph_module.build_simulation_graph
SimulationGraphState = graph_state_module.SimulationGraphState
seed_graph_state = graph_state_module.seed_graph_state
LiteLLMStructuredLLM = litellm_adapter_module.LiteLLMStructuredLLM
StructuredLLMResponseError = litellm_adapter_module.StructuredLLMResponseError
StructuredLLMTransportError = litellm_adapter_module.StructuredLLMTransportError
LLMMessage = llm_ports_module.LLMMessage
StructuredLLM = llm_ports_module.StructuredLLM
INTAKE_SYSTEM_PROMPT = intake_node_module.INTAKE_SYSTEM_PROMPT
make_intake_planner_node = intake_node_module.make_intake_planner_node
IntakePlan = intake_schema_module.IntakePlan

T = TypeVar("T", bound=BaseModel)


def _make_plan(**overrides: Any) -> IntakePlan:
    payload: dict[str, Any] = {
        "user_query": "강남구 아파트를 스트레스 테스트해줘",
        "objective": "금리 인상 시 가격 민감도를 확인한다.",
        "analysis_mode": "stress",
        "geography_hint": "강남구",
        "segment_hint": "아파트",
        "horizon_months": 12,
        "requested_shocks": ["금리인상"],
        "participant_focus": ["실수요자", "투자자"],
        "constraints": ["월 1회 업데이트"],
        "assumptions": ["정책 변화 없음"],
        "ambiguities": ["시작 시점이 불명확함"],
    }
    payload.update(overrides)
    return IntakePlan(**payload)


def _make_choice(content: str | None) -> SimpleNamespace:
    return SimpleNamespace(message=SimpleNamespace(content=content))


class FakeStructuredLLM:
    def __init__(self, response: BaseModel) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def generate_structured(
        self,
        *,
        messages: list[LLMMessage],
        response_model: type[T],
        temperature: float = 0.0,
    ) -> T:
        self.calls.append(
            {
                "messages": list(messages),
                "response_model": response_model,
                "temperature": temperature,
            }
        )
        return response_model.model_validate(self.response.model_dump())


class TestIntakePlanSchema:
    def test_valid_construction(self) -> None:
        plan = _make_plan()

        assert plan.analysis_mode == "stress"
        assert plan.horizon_months == 12
        assert plan.geography_hint == "강남구"

    def test_frozen_immutability(self) -> None:
        plan = _make_plan()

        with pytest.raises(ValidationError):
            plan.objective = "다른 목표"

    def test_field_defaults(self) -> None:
        plan = _make_plan(
            geography_hint=None,
            segment_hint=None,
            requested_shocks=[],
            participant_focus=[],
            constraints=[],
            assumptions=[],
            ambiguities=[],
        )

        assert plan.geography_hint is None
        assert plan.segment_hint is None
        assert plan.requested_shocks == []
        assert plan.participant_focus == []
        assert plan.constraints == []
        assert plan.assumptions == []
        assert plan.ambiguities == []

    @pytest.mark.parametrize("value", [1, 120])
    def test_horizon_months_accepts_boundaries(self, value: int) -> None:
        plan = _make_plan(horizon_months=value)

        assert plan.horizon_months == value

    @pytest.mark.parametrize("value", [0, 121])
    def test_horizon_months_rejects_out_of_range(self, value: int) -> None:
        with pytest.raises(ValidationError):
            _make_plan(horizon_months=value)

    def test_analysis_mode_literal_validation(self) -> None:
        with pytest.raises(ValidationError):
            _make_plan(analysis_mode="unknown")


class TestLLMPorts:
    def test_llm_message_typeddict_valid_construction(self) -> None:
        message: LLMMessage = {"role": "user", "content": "분석해줘"}

        assert message["role"] == "user"
        assert message["content"] == "분석해줘"

    def test_fake_implementation_matches_structured_llm_contract(self) -> None:
        fake = FakeStructuredLLM(_make_plan())

        def call_port(llm: StructuredLLM) -> IntakePlan:
            return llm.generate_structured(
                messages=[{"role": "user", "content": "질문"}],
                response_model=IntakePlan,
                temperature=0.0,
            )

        result = call_port(fake)

        assert isinstance(result, IntakePlan)
        assert result.user_query == _make_plan().user_query


class TestLiteLLMStructuredLLM:
    def test_calls_litellm_with_expected_args(self) -> None:
        adapter = LiteLLMStructuredLLM(model="gpt-test", api_key="secret", timeout=20)
        expected_plan = _make_plan()
        mock_litellm = MagicMock()
        mock_litellm.completion.return_value = SimpleNamespace(choices=[_make_choice(expected_plan.model_dump_json())])

        with patch.dict("sys.modules", {"litellm": mock_litellm}):
            result = adapter.generate_structured(
                messages=[{"role": "user", "content": expected_plan.user_query}],
                response_model=IntakePlan,
                temperature=0.25,
            )

        assert result == expected_plan
        mock_litellm.completion.assert_called_once()
        call_kwargs = mock_litellm.completion.call_args.kwargs
        assert call_kwargs["model"] == "gpt-test"
        assert call_kwargs["messages"] == [{"role": "user", "content": expected_plan.user_query}]
        assert call_kwargs["temperature"] == 0.25
        assert call_kwargs["api_key"] == "secret"
        assert call_kwargs["timeout"] == 20
        response_format = call_kwargs["response_format"]
        assert response_format["type"] == "json_schema"
        assert response_format["json_schema"]["name"] == "IntakePlan"
        assert response_format["json_schema"]["schema"] == IntakePlan.model_json_schema()

    def test_raises_transport_error_on_litellm_failure(self) -> None:
        adapter = LiteLLMStructuredLLM(model="gpt-test")
        mock_litellm = MagicMock()
        mock_litellm.completion.side_effect = RuntimeError("network down")

        with patch.dict("sys.modules", {"litellm": mock_litellm}):
            with pytest.raises(StructuredLLMTransportError, match="LLM call failed"):
                adapter.generate_structured(
                    messages=[{"role": "user", "content": "질문"}],
                    response_model=IntakePlan,
                )

    def test_raises_response_error_on_empty_content(self) -> None:
        adapter = LiteLLMStructuredLLM(model="gpt-test")
        mock_litellm = MagicMock()
        mock_litellm.completion.return_value = SimpleNamespace(choices=[_make_choice(None)])

        with patch.dict("sys.modules", {"litellm": mock_litellm}):
            with pytest.raises(StructuredLLMResponseError, match="empty content"):
                adapter.generate_structured(
                    messages=[{"role": "user", "content": "질문"}],
                    response_model=IntakePlan,
                )

    def test_raises_response_error_on_invalid_json(self) -> None:
        adapter = LiteLLMStructuredLLM(model="gpt-test")
        mock_litellm = MagicMock()
        mock_litellm.completion.return_value = SimpleNamespace(choices=[_make_choice("not-json")])

        with patch.dict("sys.modules", {"litellm": mock_litellm}):
            with pytest.raises(StructuredLLMResponseError, match="invalid JSON"):
                adapter.generate_structured(
                    messages=[{"role": "user", "content": "질문"}],
                    response_model=IntakePlan,
                )

    def test_raises_response_error_on_schema_validation_failure(self) -> None:
        adapter = LiteLLMStructuredLLM(model="gpt-test")
        bad_payload = json.dumps({"user_query": "질문"})
        mock_litellm = MagicMock()
        mock_litellm.completion.return_value = SimpleNamespace(choices=[_make_choice(bad_payload)])

        with patch.dict("sys.modules", {"litellm": mock_litellm}):
            with pytest.raises(StructuredLLMResponseError, match="schema validation"):
                adapter.generate_structured(
                    messages=[{"role": "user", "content": "질문"}],
                    response_model=IntakePlan,
                )


class TestIntakePlannerNode:
    def test_returns_intake_plan_and_event_refs(self) -> None:
        store = InMemoryEventStore()
        plan = _make_plan()
        llm = FakeStructuredLLM(plan)
        node = make_intake_planner_node(store, llm)
        state = seed_graph_state(plan.user_query, "run-node-001", "run-node", "gpt-test")

        result = node(state)

        assert result["intake_plan"] == plan.model_dump()
        assert len(result["event_refs"]) == 1
        assert isinstance(result["event_refs"][0], str)

    def test_emits_intake_planned_event_with_payload(self) -> None:
        store = InMemoryEventStore()
        plan = _make_plan()
        llm = FakeStructuredLLM(plan)
        node = make_intake_planner_node(store, llm)
        state = seed_graph_state(plan.user_query, "run-node-002", "run-node", "gpt-test")

        result = node(state)

        events = store.get_events_by_type("run-node-002", "INTAKE_PLANNED")
        assert len(events) == 1
        assert events[0].payload == plan.model_dump()
        assert events[0].event_id == result["event_refs"][0]
        assert events[0].round_no == 0

    def test_raises_when_run_meta_missing(self) -> None:
        store = InMemoryEventStore()
        llm = FakeStructuredLLM(_make_plan())
        node = make_intake_planner_node(store, llm)
        state: SimulationGraphState = {"user_query": "강남구 분석"}

        with pytest.raises(ValueError, match="run_meta is required"):
            node(state)

    def test_passes_system_and_user_messages_to_llm(self) -> None:
        store = InMemoryEventStore()
        plan = _make_plan(user_query="서초구 아파트 전망")
        llm = FakeStructuredLLM(plan)
        node = make_intake_planner_node(store, llm)
        state = seed_graph_state(plan.user_query, "run-node-003", "run-node", "gpt-test")

        node(state)

        assert len(llm.calls) == 1
        messages = llm.calls[0]["messages"]
        assert messages == [
            {"role": "system", "content": INTAKE_SYSTEM_PROMPT},
            {"role": "user", "content": "서초구 아파트 전망"},
        ]
        assert llm.calls[0]["response_model"] is IntakePlan
        assert llm.calls[0]["temperature"] == 0.0


class TestGraphWiring:
    def test_build_graph_uses_real_intake_node_when_structured_llm_provided(self) -> None:
        store = InMemoryEventStore()
        plan = _make_plan(user_query="강남구 비교 시나리오", analysis_mode="compare")
        llm = FakeStructuredLLM(plan)
        graph = build_simulation_graph(store, structured_llm=llm)
        seed = seed_graph_state(plan.user_query, "run-graph-real", "run-real", "gpt-test")
        seed["max_rounds"] = 0

        final = graph.invoke(seed)

        assert final["intake_plan"] == plan.model_dump()
        assert "planner_status" not in final["intake_plan"]
        assert len(llm.calls) == 1

    def test_build_graph_keeps_stub_when_structured_llm_not_provided(self) -> None:
        store = InMemoryEventStore()
        graph = build_simulation_graph(store)
        seed = seed_graph_state("기본 시나리오", "run-graph-stub", "run-stub", "gpt-test")
        seed["max_rounds"] = 0

        final = graph.invoke(seed)

        assert final["intake_plan"]["planner_status"] == "stub"
        assert final["intake_plan"]["query"] == "기본 시나리오"
