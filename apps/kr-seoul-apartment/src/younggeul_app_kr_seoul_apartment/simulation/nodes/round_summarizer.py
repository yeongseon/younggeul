from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from ..events import EventStore, SimulationEvent
from ..graph_state import SimulationGraphState


def make_round_summarizer_node(event_store: EventStore) -> Any:
    def node(state: SimulationGraphState) -> dict[str, Any]:
        run_meta = state.get("run_meta")
        if run_meta is None:
            raise ValueError("run_meta is required")

        round_no = state.get("round_no", 0)
        world = state.get("world") or {}
        participants = state.get("participants") or {}
        warnings = state.get("warnings") or []

        world_summary: dict[str, dict[str, int]] = {}
        for gu_code, segment in sorted(world.items()):
            world_summary[gu_code] = {
                "median_price": segment.current_median_price,
                "volume": segment.current_volume,
            }

        role_summary: dict[str, dict[str, Any]] = {}
        for participant in participants.values():
            role = participant.role
            if role not in role_summary:
                role_summary[role] = {"count": 0, "total_capital": 0, "total_holdings": 0}
            role_summary[role]["count"] += 1
            role_summary[role]["total_capital"] += participant.capital
            role_summary[role]["total_holdings"] += participant.holdings

        payload = {
            "total_rounds": round_no,
            "world_summary": world_summary,
            "participant_summary": role_summary,
            "total_warnings": len(warnings) if isinstance(warnings, list) else 0,
        }

        event_id = str(uuid4())
        event_store.append(
            SimulationEvent(
                event_id=event_id,
                run_id=run_meta.run_id,
                round_no=round_no,
                event_type="SIMULATION_COMPLETED",
                timestamp=datetime.now(timezone.utc),
                payload=payload,
            )
        )

        return {"event_refs": [event_id]}

    return node
