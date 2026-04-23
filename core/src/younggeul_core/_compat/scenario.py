"""abdp scenario-runner adapter primitives.

This module ships the *generic, app-agnostic* building blocks needed to drive
:mod:`abdp.scenario.ScenarioRunner` over data produced by the existing
younggeul LangGraph pipeline. The primitives live in ``core`` because they
operate purely on core's Pydantic projection types
(:mod:`younggeul_core.state.simulation`) and the abdp public contracts.

Per ADR-012 and Oracle's binding design ruling for the shadow-runner work:

* The LangGraph ``GraphState`` (in ``apps/``) remains the canonical state
  representation. ``SimulationState`` (here, in ``core``) and abdp's
  :class:`abdp.simulation.SimulationState` are runner-boundary projections.
* Adapters are *thin* wrappers - they MUST NOT re-implement younggeul
  decision or resolution logic. Forking parity is forbidden.
* Synthesized identifiers (Seed, scenario_key, snapshot UUID, proposal_id)
  are runner-internal and never surface in user-facing CLI text or
  younggeul-owned PK storage.

The adapter classes here are intentionally generic (callable-backed).
The actual wiring of younggeul's ``ParticipantPolicy.decide`` and the
``round_resolver`` math into these adapters is performed in the shadow-runner slice at the
``apps/kr-seoul-apartment/`` layer (which is permitted to depend on core).
That layered split preserves the strict ``core <- apps`` dependency rule.
"""

from __future__ import annotations

# pyright: reportMissingImports=false

import hashlib
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Final, Generic, Literal, TypeVar, cast
from uuid import UUID, uuid5

from younggeul_core.state.simulation import (
    ActionProposal as YgActionProposal,
)
from younggeul_core.state.simulation import (
    ParticipantState as YgParticipantState,
)
from younggeul_core.state.simulation import (
    SegmentState as YgSegmentState,
)

from younggeul_core._compat import require_abdp
from younggeul_core._compat.ids import (
    DEFAULT_SHADOW_SEED,
    SnapshotIdRegistry,
    YOUNGGEUL_SNAPSHOT_NAMESPACE,
)

__all__ = [
    "PROPOSAL_ID_NAMESPACE",
    "AbdpActionAdapter",
    "AbdpParticipantAdapter",
    "AbdpSegmentAdapter",
    "CallableAgent",
    "CallableResolver",
    "derive_proposal_id",
    "project_audit_log",
    "to_abdp_simulation_state",
    "to_abdp_snapshot_ref",
]

# UUID5 namespace for synthesized abdp ActionProposal.proposal_id values.
# Frozen literal: rotating it would invalidate previously-derived proposal_ids
# and break audit-log replay determinism.
PROPOSAL_ID_NAMESPACE: Final[UUID] = UUID("8b2d6b06-6f4f-5b0a-9f2e-abc123450002")

# Default tier when projecting younggeul SnapshotRef -> abdp SnapshotRef.
# younggeul's snapshot tier metadata is not exposed on the core Pydantic
# SnapshotRef, so we use "silver" as the safe default (matches the typical
# tier of normalized data fed into the simulation plane).
_AbdpSnapshotTier = Literal["bronze", "silver", "gold"]
_DEFAULT_ABDP_SNAPSHOT_TIER: Final[_AbdpSnapshotTier] = "silver"


@dataclass(frozen=True, slots=True)
class AbdpSegmentAdapter:
    """abdp.simulation.SegmentState Protocol adapter over core SegmentState.

    Exposes ``segment_id`` (= ``gu_code``) and ``participant_ids`` (caller
    supplies, since younggeul models segment <-> participant association
    in the round resolver, not on the segment itself). The wrapped
    ``inner`` is preserved for downstream consumers that need the
    full Pydantic data.
    """

    segment_id: str
    participant_ids: tuple[str, ...]
    inner: YgSegmentState

    @classmethod
    def from_core(
        cls,
        segment: YgSegmentState,
        *,
        participant_ids: Iterable[str] = (),
    ) -> AbdpSegmentAdapter:
        return cls(
            segment_id=segment.gu_code,
            participant_ids=tuple(participant_ids),
            inner=segment,
        )


@dataclass(frozen=True, slots=True)
class AbdpParticipantAdapter:
    """abdp.simulation.ParticipantState Protocol adapter over core ParticipantState."""

    participant_id: str
    inner: YgParticipantState

    @classmethod
    def from_core(cls, participant: YgParticipantState) -> AbdpParticipantAdapter:
        return cls(
            participant_id=participant.participant_id,
            inner=participant,
        )


@dataclass(frozen=True, slots=True)
class AbdpActionAdapter:
    """abdp.simulation.ActionProposal Protocol adapter over core ActionProposal.

    Maps:

    * ``proposal_id`` <- :func:`derive_proposal_id` (deterministic uuid5).
    * ``actor_id``    <- core ``agent_id``.
    * ``action_key``  <- core ``action_type``.
    * ``payload``     <- ``model_dump(mode="json")`` of the wrapped action.
    """

    proposal_id: str
    actor_id: str
    action_key: str
    payload: Mapping[str, Any]
    inner: YgActionProposal

    @classmethod
    def from_core(cls, action: YgActionProposal) -> AbdpActionAdapter:
        return cls(
            proposal_id=str(derive_proposal_id(action)),
            actor_id=action.agent_id,
            action_key=action.action_type,
            payload=action.model_dump(mode="json"),
            inner=action,
        )


def derive_proposal_id(action: YgActionProposal) -> UUID:
    """Derive a deterministic, runner-internal abdp proposal_id from a core ActionProposal.

    The id is uuid5(:data:`PROPOSAL_ID_NAMESPACE`, "<agent_id>:<round_no>:<action_type>:<target_segment>:<sha256(reasoning_summary)>").

    Stable across runs for the same logical proposal. Different proposals
    from the same agent in the same round on the same segment are
    disambiguated by ``reasoning_summary`` hashing - callers that need
    stronger collision resistance should keep ``reasoning_summary``
    deterministic per proposal.
    """
    reasoning_digest = hashlib.sha256(action.reasoning_summary.encode("utf-8")).hexdigest()
    name = f"{action.agent_id}:{action.round_no}:{action.action_type}:{action.target_segment}:{reasoning_digest}"
    return uuid5(PROPOSAL_ID_NAMESPACE, name)


def to_abdp_snapshot_ref(
    *,
    sha256_hex: str,
    storage_key: str,
    registry: SnapshotIdRegistry,
    tier: _AbdpSnapshotTier = _DEFAULT_ABDP_SNAPSHOT_TIER,
) -> Any:
    """Project a younggeul snapshot sha256 hex into an :class:`abdp.simulation.SnapshotRef`.

    Registers the sha256 with the supplied :class:`SnapshotIdRegistry` so the
    bijection (uuid <-> sha256) is preserved for the run. The abdp
    ``SnapshotRef`` requires:

    * ``snapshot_id``: UUID (we synthesize via uuid5 with
      :data:`younggeul_core._compat.ids.YOUNGGEUL_SNAPSHOT_NAMESPACE`).
    * ``tier``: one of ``"bronze"``, ``"silver"``, ``"gold"``.
    * ``storage_key``: non-empty string.

    Args:
        sha256_hex: 64-char lowercase hex digest of the canonical snapshot.
        storage_key: Caller-supplied storage path/key (non-empty).
        registry: Registry that records the (uuid, sha256) bijection.
        tier: abdp snapshot tier; defaults to ``"silver"``.

    Returns:
        An :class:`abdp.simulation.SnapshotRef` instance.
    """
    require_abdp()
    from abdp.simulation import SnapshotRef as AbdpSnapshotRef  # type: ignore[import-not-found,unused-ignore]

    snapshot_uuid = registry.register(sha256_hex)
    return AbdpSnapshotRef(snapshot_id=snapshot_uuid, tier=tier, storage_key=storage_key)


def to_abdp_simulation_state(
    *,
    segments: Iterable[YgSegmentState],
    participants: Iterable[YgParticipantState],
    snapshot_ref: Any,
    pending_actions: Iterable[YgActionProposal] = (),
    seed: int = DEFAULT_SHADOW_SEED,
    step_index: int = 0,
    segment_participants: Mapping[str, Iterable[str]] | None = None,
) -> Any:
    """Project core simulation pieces into a frozen :class:`abdp.simulation.SimulationState`.

    Tuple ordering is preserved exactly as supplied by the caller so the
    projection is deterministic. ``segment_participants`` lets the caller
    record which participant ids belong to each segment (keyed by
    ``segment.gu_code``); segments not present in the mapping receive an
    empty ``participant_ids`` tuple.

    Args:
        segments: Core SegmentState instances (ordering preserved).
        participants: Core ParticipantState instances (ordering preserved).
        snapshot_ref: An :class:`abdp.simulation.SnapshotRef` from
            :func:`to_abdp_snapshot_ref`.
        pending_actions: Actions to carry as ``pending_actions`` on the
            initial state (typically empty for shadow runs from a fresh
            scenario).
        seed: Runner-internal abdp Seed (default ``DEFAULT_SHADOW_SEED``).
        step_index: Initial step index (default ``0``).
        segment_participants: Optional mapping ``gu_code -> participant_ids``.

    Returns:
        A frozen :class:`abdp.simulation.SimulationState` instance.
    """
    require_abdp()
    from abdp.core import Seed  # type: ignore[import-not-found,unused-ignore]
    from abdp.simulation import SimulationState as AbdpSimulationState  # type: ignore[import-not-found,unused-ignore]

    seg_part_map = {key: tuple(value) for key, value in (segment_participants or {}).items()}
    segment_adapters = tuple(
        AbdpSegmentAdapter.from_core(seg, participant_ids=seg_part_map.get(seg.gu_code, ())) for seg in segments
    )
    participant_adapters = tuple(AbdpParticipantAdapter.from_core(p) for p in participants)
    pending_adapters = tuple(AbdpActionAdapter.from_core(a) for a in pending_actions)

    return AbdpSimulationState(
        step_index=step_index,
        seed=cast(Any, Seed(seed)),
        snapshot_ref=snapshot_ref,
        segments=segment_adapters,
        participants=participant_adapters,
        pending_actions=cast(Any, pending_adapters),
    )


_S = TypeVar("_S")
_P = TypeVar("_P")
_A = TypeVar("_A")


@dataclass(frozen=True, slots=True)
class CallableAgent(Generic[_S, _P, _A]):
    """Generic abdp.agents.Agent Protocol adapter wrapping a decide callable.

    The wrapped callable receives an :class:`abdp.agents.AgentContext` and
    must return an :class:`abdp.agents.AgentDecision`. younggeul-app
    callables from the shadow-runner slice translate the AgentContext into the form expected by
    ``ParticipantPolicy.decide`` and project the result back.
    """

    agent_id: str
    decide_fn: Callable[[Any], Any] = field(compare=False)

    def decide(self, context: Any) -> Any:
        return self.decide_fn(context)


@dataclass(frozen=True, slots=True)
class CallableResolver(Generic[_S, _P, _A]):
    """Generic abdp.scenario.ActionResolver Protocol adapter wrapping a resolve callable.

    The wrapped callable receives ``(state, proposals)`` (matching abdp's
    ActionResolver.resolve signature) and must return the next
    :class:`abdp.simulation.SimulationState`.

    Per the abdp contract: implementations MUST NOT mutate the input
    ``state``. The wrapped callable is responsible for upholding that.
    """

    resolve_fn: Callable[[Any, tuple[Any, ...]], Any] = field(compare=False)

    def resolve(self, state: Any, proposals: tuple[Any, ...]) -> Any:
        return self.resolve_fn(state, proposals)


def project_audit_log(
    *,
    scenario_run: Any,
    summary: Any,
    evidence: tuple[Any, ...] = (),
    claims: tuple[Any, ...] = (),
) -> Any:
    """Project an :class:`abdp.scenario.ScenarioRun` into an :class:`abdp.evidence.AuditLog`.

    The abdp ``AuditLog.__post_init__`` enforces:

    * ``scenario_key == run.scenario_key``
    * ``seed == run.seed``

    This helper passes the run's own ``scenario_key`` and ``seed`` through
    so the invariants always hold. ``evidence`` and ``claims`` ordering is
    preserved verbatim (abdp does not impose canonical ordering at this
    layer; deterministic ordering is the caller's responsibility).

    Args:
        scenario_run: The :class:`abdp.scenario.ScenarioRun` produced by
            :class:`abdp.scenario.ScenarioRunner`.
        summary: An :class:`abdp.evaluation.summary.EvaluationSummary`.
        evidence: Tuple of :class:`abdp.evidence.EvidenceRecord` (default empty).
        claims: Tuple of :class:`abdp.evidence.ClaimRecord` (default empty).

    Returns:
        A frozen :class:`abdp.evidence.AuditLog` instance.
    """
    require_abdp()
    from abdp.evidence import AuditLog  # type: ignore[import-not-found,unused-ignore]

    return AuditLog(
        scenario_key=scenario_run.scenario_key,
        seed=scenario_run.seed,
        run=scenario_run,
        summary=summary,
        evidence=evidence,
        claims=claims,
    )


__all__ += ["DEFAULT_SHADOW_SEED", "YOUNGGEUL_SNAPSHOT_NAMESPACE"]
