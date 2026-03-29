from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


class SimulationEvent(BaseModel):
    """A single typed event in the simulation event log."""

    model_config = ConfigDict(frozen=True)

    event_id: str
    run_id: str
    round_no: int = Field(ge=0)
    event_type: str
    timestamp: datetime
    payload: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class EventStore(Protocol):
    """Protocol for event storage backends."""

    def append(self, event: SimulationEvent) -> None:
        """Append a single event. Must be thread-safe."""

        ...

    def get_events(self, run_id: str) -> list[SimulationEvent]:
        """Return all events for a given run_id, ordered by timestamp."""

        ...

    def get_events_by_type(self, run_id: str, event_type: str) -> list[SimulationEvent]:
        """Return events filtered by run_id and event_type."""

        ...

    def count(self, run_id: str) -> int:
        """Return the number of events for a given run_id."""

        ...

    def clear(self, run_id: str) -> None:
        """Remove all events for a given run_id."""

        ...
