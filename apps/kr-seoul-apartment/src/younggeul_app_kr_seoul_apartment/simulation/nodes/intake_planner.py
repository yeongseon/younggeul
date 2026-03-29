from __future__ import annotations

from typing import Any

from ..events import EventStore, SimulationEvent
from ..graph_state import SimulationGraphState
from ..llm.ports import LLMMessage, StructuredLLM
from ..schemas.intake import IntakePlan

INTAKE_SYSTEM_PROMPT = """You are the intake planner for a Korean real-estate simulation engine.

Given the user's natural-language query, extract a structured IntakePlan.

Guidelines:
- analysis_mode: "baseline" for simple what-if, "stress" for adverse scenario, "compare" for A/B comparison.
- geography_hint: Korean district name if mentioned (e.g., "강남구", "서초구").
- segment_hint: Property type/segment if mentioned (e.g., "아파트", "오피스텔").
- horizon_months: Simulation horizon in months (default 12 if not specified).
- requested_shocks: External shocks mentioned (e.g., "금리인상", "공급확대").
- participant_focus: Types of market participants to model (e.g., "실수요자", "투자자").
- constraints and assumptions: Any explicit constraints or assumptions stated.
- ambiguities: List anything unclear in the user's query that might affect simulation accuracy.
- Always preserve the original user_query verbatim.
- objective: One-sentence summary of what the user wants to learn.
"""


def make_intake_planner_node(
    event_store: EventStore,
    structured_llm: StructuredLLM,
) -> Any:
    def node(state: SimulationGraphState) -> dict[str, Any]:
        from datetime import datetime, timezone
        from uuid import uuid4

        user_query = state.get("user_query", "")

        messages: list[LLMMessage] = [
            {"role": "system", "content": INTAKE_SYSTEM_PROMPT},
            {"role": "user", "content": user_query},
        ]

        plan = structured_llm.generate_structured(
            messages=messages,
            response_model=IntakePlan,
            temperature=0.0,
        )

        event_id = str(uuid4())
        run_meta = state.get("run_meta")
        if run_meta is None:
            msg = "run_meta is required before emitting simulation events"
            raise ValueError(msg)

        event = SimulationEvent(
            event_id=event_id,
            run_id=run_meta.run_id,
            round_no=0,
            event_type="INTAKE_PLANNED",
            timestamp=datetime.now(timezone.utc),
            payload=plan.model_dump(),
        )
        event_store.append(event)

        return {
            "intake_plan": plan.model_dump(),
            "event_refs": [event_id],
        }

    return node
