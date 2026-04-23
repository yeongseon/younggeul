"""abdp shadow runner wiring (M9'-c).

Drives :class:`abdp.scenario.ScenarioRunner` over younggeul's existing
participant-policy and round-resolver logic by composing the M9'-b
adapter primitives in :mod:`younggeul_core._compat.scenario` with the
pure resolution math in :mod:`.nodes._resolver_math` and the policy
registry in :mod:`.policies`.

Per Oracle's M9' design ruling F (REAL SHADOW EXECUTION, not synthesis):
the agents and resolver here MUST call the same decide/resolve logic the
LangGraph nodes call, never a fork. They do: each
:class:`younggeul_core._compat.scenario.CallableAgent` invokes
``ParticipantPolicy.decide`` exactly as the participant decider node
does, and the :class:`younggeul_core._compat.scenario.CallableResolver`
delegates to :func:`pure_resolve_round` exactly as the round resolver
node does.

The seed, scenario_key, snapshot UUID, and proposal_id values surfaced
to abdp are runner-internal and never appear in user-facing CLI text or
younggeul-owned PK storage (Oracle ruling D).
"""

from __future__ import annotations

# pyright: reportMissingImports=false

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Final, cast

from younggeul_core._compat import require_abdp
from younggeul_core._compat.ids import (
    DEFAULT_SHADOW_SEED,
    SnapshotIdRegistry,
    derive_scenario_key,
)
from younggeul_core._compat.scenario import (
    AbdpActionAdapter,
    CallableAgent,
    CallableResolver,
    project_audit_log,
    to_abdp_simulation_state,
    to_abdp_snapshot_ref,
)
from younggeul_core.state.simulation import (
    ActionProposal,
    ParticipantState,
    ScenarioSpec,
    SegmentState,
    Shock,
)

from .graph_state import SimulationGraphState
from .nodes._resolver_math import pure_resolve_round
from .policies.protocol import ParticipantPolicy
from .policies.registry import get_default_policy
from .schemas.round import DecisionContext

DEFAULT_SHADOW_MAX_STEPS: Final[int] = 16

_SHOCK_MODIFIER_KEYS: dict[str, str] = {
    "interest_rate": "interest_rate_delta",
    "regulation": "regulation_severity",
    "supply": "supply_delta",
    "demand": "demand_delta",
}


@dataclass(frozen=True, slots=True)
class _ShadowAgentDecision:
    agent_id: str
    proposals: tuple[Any, ...]


@dataclass(frozen=True, slots=True)
class _ShadowScenarioSpec:
    """Concrete :class:`abdp.simulation.ScenarioSpec` for a shadow run."""

    scenario_key: str
    seed: int
    initial_state: Any = field(compare=False)

    def build_initial_state(self) -> Any:
        return self.initial_state


def _derive_governance_modifiers(shocks: Sequence[Shock]) -> dict[str, float]:
    modifiers: dict[str, float] = {}
    for shock in shocks:
        modifier_key = _SHOCK_MODIFIER_KEYS.get(shock.shock_type)
        if modifier_key is None:
            continue
        modifiers[modifier_key] = modifiers.get(modifier_key, 0.0) + shock.magnitude
    return modifiers


def _resolve_target_segment(world: dict[str, SegmentState], scenario: ScenarioSpec) -> SegmentState:
    if not world:
        raise ValueError("world must contain at least one segment")
    target_gu = scenario.target_gus[0] if scenario.target_gus else None
    if target_gu is not None and target_gu in world:
        return world[target_gu]
    return next(iter(world.values()))


def _world_from_state(state: Any, segment_order: tuple[str, ...]) -> dict[str, SegmentState]:
    by_id: dict[str, SegmentState] = {seg.segment_id: seg.inner for seg in state.segments}
    return {gu_code: by_id[gu_code] for gu_code in segment_order if gu_code in by_id}


def _participants_from_state(state: Any, participant_order: tuple[str, ...]) -> dict[str, ParticipantState]:
    by_id: dict[str, ParticipantState] = {p.participant_id: p.inner for p in state.participants}
    return {pid: by_id[pid] for pid in participant_order if pid in by_id}


def _make_shadow_agent(
    *,
    participant_id: str,
    scenario: ScenarioSpec,
    segment_order: tuple[str, ...],
    policy_lookup: Any,
) -> CallableAgent[Any, Any, Any]:
    """Wrap a younggeul participant policy as an abdp Agent.

    The wrapped callable receives an :class:`abdp.agents.AgentContext`,
    extracts the current participant + world from
    ``context.state``, builds a :class:`DecisionContext` exactly as the
    LangGraph participant decider node does, and returns a single-proposal
    :class:`abdp.agents.AgentDecision`.
    """

    def decide_fn(context: Any) -> _ShadowAgentDecision:
        state = context.state
        world = _world_from_state(state, segment_order)
        participants_by_id = {p.participant_id: p.inner for p in state.participants}
        participant = participants_by_id[participant_id]
        round_no = int(context.step_index) + 1
        target_segment = _resolve_target_segment(world, scenario)
        active_shocks = list(scenario.shocks)
        decision_ctx = DecisionContext(
            round_no=round_no,
            segment=target_segment,
            scenario=scenario,
            last_outcome=None,
            active_shocks=active_shocks,
            governance_modifiers=_derive_governance_modifiers(active_shocks),
        )
        policy: ParticipantPolicy = policy_lookup(participant.role)
        proposal: ActionProposal = policy.decide(participant, decision_ctx)
        return _ShadowAgentDecision(
            agent_id=participant_id,
            proposals=(AbdpActionAdapter.from_core(proposal),),
        )

    return CallableAgent(agent_id=participant_id, decide_fn=decide_fn)


def _make_shadow_resolver(
    *,
    snapshot_ref: Any,
    seed: int,
    segment_order: tuple[str, ...],
    participant_order: tuple[str, ...],
    segment_participants: dict[str, tuple[str, ...]],
) -> CallableResolver[Any, Any, Any]:
    """Wrap :func:`pure_resolve_round` as an abdp ActionResolver."""

    def resolve_fn(state: Any, proposals: tuple[Any, ...]) -> Any:
        world = _world_from_state(state, segment_order)
        participants = _participants_from_state(state, participant_order)
        market_actions = {p.actor_id: p.inner for p in proposals}
        round_no = int(state.step_index) + 1
        result = pure_resolve_round(
            world=world,
            participants=participants,
            market_actions=market_actions,
            round_no=round_no,
        )
        return to_abdp_simulation_state(
            segments=[result.new_world[gu] for gu in segment_order if gu in result.new_world],
            participants=[result.new_participants[pid] for pid in participant_order if pid in result.new_participants],
            snapshot_ref=snapshot_ref,
            pending_actions=(),
            seed=seed,
            step_index=int(state.step_index) + 1,
            segment_participants=segment_participants,
        )

    return CallableResolver(resolve_fn=resolve_fn)


def _segment_participants_map(
    participants: dict[str, ParticipantState],
    scenario: ScenarioSpec,
    world: dict[str, SegmentState],
) -> dict[str, tuple[str, ...]]:
    if not world:
        return {}
    target = _resolve_target_segment(world, scenario)
    mapping: dict[str, tuple[str, ...]] = {gu: () for gu in world}
    mapping[target.gu_code] = tuple(participants.keys())
    return mapping


def run_shadow_audit(
    initial_graph_state: SimulationGraphState,
    *,
    snapshot_sha256_hex: str,
    snapshot_storage_key: str,
    max_steps: int = DEFAULT_SHADOW_MAX_STEPS,
    seed: int = DEFAULT_SHADOW_SEED,
    summary: Any | None = None,
    policy_registry: Any | None = None,
) -> Any:
    """Drive :class:`abdp.scenario.ScenarioRunner` over the same decision/
    resolution logic younggeul's LangGraph uses, returning a frozen
    :class:`abdp.evidence.AuditLog` that aggregates the resulting
    :class:`abdp.scenario.ScenarioRun` with an
    :class:`abdp.evaluation.EvaluationSummary`.

    Args:
        initial_graph_state: An initialized younggeul simulation graph
            state (must satisfy :func:`validate_initialized_state`).
        snapshot_sha256_hex: 64-char hex digest of the canonical snapshot
            (used to derive a runner-internal abdp ``SnapshotRef``).
        snapshot_storage_key: Caller-supplied storage path/key for the
            abdp ``SnapshotRef``.
        max_steps: Upper bound on shadow scenario steps (default 16).
        seed: Runner-internal abdp seed (default
            :data:`DEFAULT_SHADOW_SEED`).
        summary: Optional pre-built ``EvaluationSummary``; defaults to an
            empty PASS summary.
        policy_registry: Optional ``role -> ParticipantPolicy`` resolver;
            defaults to :func:`get_default_policy`.

    Returns:
        A frozen :class:`abdp.evidence.AuditLog`.
    """
    require_abdp()
    from abdp.evaluation import EvaluationSummary, GateStatus  # type: ignore[import-not-found,unused-ignore]
    from abdp.scenario import ScenarioRunner  # type: ignore[import-not-found,unused-ignore]

    scenario = initial_graph_state.get("scenario")
    if scenario is None:
        raise ValueError("initial_graph_state must include a scenario")
    world = initial_graph_state.get("world")
    if not world:
        raise ValueError("initial_graph_state must include a non-empty world")
    participants = initial_graph_state.get("participants", {})

    policy_lookup = policy_registry or get_default_policy

    registry = SnapshotIdRegistry()
    snapshot_ref = to_abdp_snapshot_ref(
        sha256_hex=snapshot_sha256_hex,
        storage_key=snapshot_storage_key,
        registry=registry,
    )

    segment_order = tuple(world.keys())
    participant_order = tuple(participants.keys())
    seg_part = _segment_participants_map(participants, scenario, world)

    initial_state = to_abdp_simulation_state(
        segments=list(world.values()),
        participants=list(participants.values()),
        snapshot_ref=snapshot_ref,
        pending_actions=(),
        seed=seed,
        step_index=0,
        segment_participants=seg_part,
    )

    scenario_key = derive_scenario_key(scenario)
    spec = _ShadowScenarioSpec(scenario_key=scenario_key, seed=seed, initial_state=initial_state)

    agents = tuple(
        _make_shadow_agent(
            participant_id=pid,
            scenario=scenario,
            segment_order=segment_order,
            policy_lookup=policy_lookup,
        )
        for pid in participant_order
    )
    resolver = _make_shadow_resolver(
        snapshot_ref=snapshot_ref,
        seed=seed,
        segment_order=segment_order,
        participant_order=participant_order,
        segment_participants=seg_part,
    )

    runner = ScenarioRunner(agents=cast(Any, agents), resolver=resolver, max_steps=max_steps)
    scenario_run = runner.run(cast(Any, spec))

    if summary is None:
        summary = EvaluationSummary(metrics=(), gates=(), overall_status=GateStatus.PASS)

    return project_audit_log(scenario_run=scenario_run, summary=summary)


__all__ = [
    "DEFAULT_SHADOW_MAX_STEPS",
    "run_shadow_audit",
]
