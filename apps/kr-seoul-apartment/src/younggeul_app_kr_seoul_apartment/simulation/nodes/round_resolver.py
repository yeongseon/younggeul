"""Round resolver node that applies actions and updates world state."""

from __future__ import annotations

# pyright: reportMissingImports=false

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from ..events import EventStore, SimulationEvent
from ..graph_state import SimulationGraphState
from ._resolver_math import pure_resolve_round


def make_round_resolver_node(event_store: EventStore) -> Any:
    """Create the round resolver node for the simulation graph.

    The round resolver node validates participant actions, resolves simulated
    transactions via :func:`pure_resolve_round`, and emits a round outcome event.

    Args:
        event_store: Event store used to publish round resolution events.

    Returns:
        A LangGraph-compatible node function.
    """

    def node(state: SimulationGraphState) -> dict[str, Any]:
        run_meta = state.get("run_meta")
        if run_meta is None:
            raise ValueError("run_meta is required")

        world = state.get("world")
        if world is None:
            raise ValueError("world is required")

        round_no = state.get("round_no", 0)
        participants = state.get("participants", {})
        market_actions = state.get("market_actions") or {}

        result = pure_resolve_round(
            world=world,
            participants=participants,
            market_actions=market_actions,
            round_no=round_no,
        )

        event_id = str(uuid4())
        event_store.append(
            SimulationEvent(
                event_id=event_id,
                run_id=run_meta.run_id,
                round_no=round_no,
                event_type="ROUND_RESOLVED",
                timestamp=datetime.now(timezone.utc),
                payload=result.payload.model_dump(),
            )
        )

        return {
            "world": result.new_world,
            "participants": result.new_participants,
            "last_outcome": result.outcome,
            "event_refs": [event_id],
            "warnings": result.warnings,
        }

    return node
