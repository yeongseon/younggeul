from __future__ import annotations

# pyright: reportMissingImports=false

from typing import Protocol, runtime_checkable

from younggeul_core.state.simulation import ActionProposal, ParticipantState

from ..schemas.round import DecisionContext


@runtime_checkable
class ParticipantPolicy(Protocol):
    def decide(self, participant: ParticipantState, context: DecisionContext) -> ActionProposal: ...
