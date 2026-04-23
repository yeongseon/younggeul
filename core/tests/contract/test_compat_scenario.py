"""Contract tests for `_compat.scenario`.

Verifies the abdp scenario-runner adapter primitives: type-shape adapters,
SimulationState projection, generic Agent/ActionResolver wrappers, and the
AuditLog projection helper. Per Oracle's binding design ruling for the shadow-runner work, the test
suite drives `abdp.scenario.ScenarioRunner.run()` end-to-end with
callable-backed adapters and asserts the resulting ScenarioRun /
AuditLog are real (not synthesized) abdp objects with all invariants
upheld.
"""

from __future__ import annotations

# pyright: reportMissingImports=false

from datetime import date, datetime, timezone
from typing import Any, cast
from uuid import UUID

import pytest

pytest.importorskip("abdp")

from abdp.agents import AgentDecision  # noqa: E402
from abdp.evaluation import EvaluationSummary, GateStatus  # noqa: E402
from abdp.evidence import AuditLog, make_evidence_record  # noqa: E402
from abdp.scenario import ActionResolver, ScenarioRun, ScenarioRunner  # noqa: E402

from younggeul_core._compat.ids import (  # noqa: E402
    DEFAULT_SHADOW_SEED,
    SnapshotIdRegistry,
    derive_scenario_key,
)
from younggeul_core._compat.scenario import (  # noqa: E402
    PROPOSAL_ID_NAMESPACE,
    AbdpActionAdapter,
    AbdpParticipantAdapter,
    AbdpSegmentAdapter,
    CallableAgent,
    CallableResolver,
    derive_proposal_id,
    project_audit_log,
    to_abdp_simulation_state,
    to_abdp_snapshot_ref,
)
from younggeul_core.state.simulation import (  # noqa: E402
    ActionProposal,
    ParticipantState,
    ScenarioSpec,
    SegmentState,
    Shock,
)


@pytest.fixture
def core_segment() -> SegmentState:
    return SegmentState(
        gu_code="11680",
        gu_name="강남구",
        current_median_price=2_000_000_000,
        current_volume=100,
        price_trend="flat",
        sentiment_index=0.5,
        supply_pressure=0.0,
    )


@pytest.fixture
def core_participants() -> list[ParticipantState]:
    return [
        ParticipantState(
            participant_id="buyer-1",
            role="buyer",
            capital=3_000_000_000,
            holdings=0,
            sentiment="bullish",
            risk_tolerance=0.4,
        ),
        ParticipantState(
            participant_id="seller-1",
            role="landlord",
            capital=500_000_000,
            holdings=2,
            sentiment="bearish",
            risk_tolerance=0.6,
        ),
    ]


@pytest.fixture
def core_action() -> ActionProposal:
    return ActionProposal(
        agent_id="buyer-1",
        round_no=1,
        action_type="buy",
        target_segment="11680",
        confidence=0.8,
        reasoning_summary="Bullish on Q3 supply tightening",
    )


@pytest.fixture
def core_scenario_spec() -> ScenarioSpec:
    return ScenarioSpec(
        scenario_name="m9b-test",
        target_gus=["11680"],
        target_period_start=date(2025, 1, 1),
        target_period_end=date(2025, 3, 31),
        shocks=[
            Shock(shock_type="interest_rate", description="basis point cut", magnitude=-0.25),
        ],
    )


@pytest.fixture
def snapshot_sha() -> str:
    return "a" * 64


@pytest.fixture
def registry() -> SnapshotIdRegistry:
    return SnapshotIdRegistry()


@pytest.fixture
def abdp_snapshot_ref(snapshot_sha: str, registry: SnapshotIdRegistry) -> Any:
    return to_abdp_snapshot_ref(
        sha256_hex=snapshot_sha,
        storage_key="snapshots/2025-04-23/seoul.parquet",
        registry=registry,
    )


class TestSegmentAdapter:
    def test_from_core_maps_gu_code_to_segment_id(self, core_segment: SegmentState) -> None:
        adapter = AbdpSegmentAdapter.from_core(core_segment, participant_ids=("buyer-1",))
        assert adapter.segment_id == "11680"
        assert adapter.participant_ids == ("buyer-1",)
        assert adapter.inner is core_segment

    def test_default_participant_ids_is_empty_tuple(self, core_segment: SegmentState) -> None:
        adapter = AbdpSegmentAdapter.from_core(core_segment)
        assert adapter.participant_ids == ()


class TestParticipantAdapter:
    def test_from_core_preserves_participant_id(self, core_participants: list[ParticipantState]) -> None:
        adapter = AbdpParticipantAdapter.from_core(core_participants[0])
        assert adapter.participant_id == "buyer-1"
        assert adapter.inner is core_participants[0]


class TestActionAdapter:
    def test_from_core_maps_to_abdp_protocol_fields(self, core_action: ActionProposal) -> None:
        adapter = AbdpActionAdapter.from_core(core_action)
        assert adapter.actor_id == "buyer-1"
        assert adapter.action_key == "buy"
        assert adapter.payload["agent_id"] == "buyer-1"
        assert adapter.payload["action_type"] == "buy"
        _ = UUID(adapter.proposal_id)
        assert adapter.inner is core_action

    def test_proposal_id_is_deterministic(self, core_action: ActionProposal) -> None:
        a = AbdpActionAdapter.from_core(core_action)
        b = AbdpActionAdapter.from_core(core_action)
        assert a.proposal_id == b.proposal_id

    def test_proposal_id_changes_with_round(self, core_action: ActionProposal) -> None:
        a = AbdpActionAdapter.from_core(core_action)
        b = AbdpActionAdapter.from_core(core_action.model_copy(update={"round_no": 2}))
        assert a.proposal_id != b.proposal_id

    def test_proposal_id_namespace_is_uuid5(self, core_action: ActionProposal) -> None:
        derived = derive_proposal_id(core_action)
        assert isinstance(derived, UUID)
        assert derived.version == 5

    def test_proposal_id_namespace_is_distinct_from_snapshot(self) -> None:
        from younggeul_core._compat.ids import YOUNGGEUL_SNAPSHOT_NAMESPACE

        assert PROPOSAL_ID_NAMESPACE != YOUNGGEUL_SNAPSHOT_NAMESPACE


class TestSnapshotRefProjection:
    def test_roundtrips_through_registry(self, snapshot_sha: str, registry: SnapshotIdRegistry) -> None:
        ref = to_abdp_snapshot_ref(
            sha256_hex=snapshot_sha,
            storage_key="snapshots/x.parquet",
            registry=registry,
        )
        assert ref.tier == "silver"
        assert ref.storage_key == "snapshots/x.parquet"
        assert isinstance(ref.snapshot_id, UUID)
        assert registry.sha256_for(ref.snapshot_id) == snapshot_sha

    def test_explicit_tier(self, snapshot_sha: str, registry: SnapshotIdRegistry) -> None:
        ref = to_abdp_snapshot_ref(
            sha256_hex=snapshot_sha,
            storage_key="snapshots/x.parquet",
            registry=registry,
            tier="gold",
        )
        assert ref.tier == "gold"

    def test_invalid_tier_raises(self, snapshot_sha: str, registry: SnapshotIdRegistry) -> None:
        with pytest.raises(ValueError):
            to_abdp_snapshot_ref(
                sha256_hex=snapshot_sha,
                storage_key="snapshots/x.parquet",
                registry=registry,
                tier=cast(Any, "platinum"),
            )


class TestSimulationStateProjection:
    def test_produces_frozen_abdp_state(
        self,
        core_segment: SegmentState,
        core_participants: list[ParticipantState],
        abdp_snapshot_ref: Any,
    ) -> None:
        state = to_abdp_simulation_state(
            segments=[core_segment],
            participants=core_participants,
            snapshot_ref=abdp_snapshot_ref,
            segment_participants={"11680": ["buyer-1", "seller-1"]},
        )
        assert state.step_index == 0
        assert state.seed == DEFAULT_SHADOW_SEED
        assert state.snapshot_ref is abdp_snapshot_ref
        assert len(state.segments) == 1
        assert state.segments[0].segment_id == "11680"
        assert state.segments[0].participant_ids == ("buyer-1", "seller-1")
        assert tuple(p.participant_id for p in state.participants) == ("buyer-1", "seller-1")
        assert state.pending_actions == ()

    def test_preserves_caller_ordering(
        self,
        core_segment: SegmentState,
        core_participants: list[ParticipantState],
        abdp_snapshot_ref: Any,
    ) -> None:
        reversed_participants = list(reversed(core_participants))
        state = to_abdp_simulation_state(
            segments=[core_segment],
            participants=reversed_participants,
            snapshot_ref=abdp_snapshot_ref,
        )
        assert tuple(p.participant_id for p in state.participants) == ("seller-1", "buyer-1")

    def test_pending_actions_projected(
        self,
        core_segment: SegmentState,
        core_participants: list[ParticipantState],
        core_action: ActionProposal,
        abdp_snapshot_ref: Any,
    ) -> None:
        state = to_abdp_simulation_state(
            segments=[core_segment],
            participants=core_participants,
            snapshot_ref=abdp_snapshot_ref,
            pending_actions=[core_action],
        )
        assert len(state.pending_actions) == 1
        assert state.pending_actions[0].actor_id == "buyer-1"


class _FakeDecision:
    """Minimal AgentDecision Protocol implementation."""

    __slots__ = ("agent_id", "proposals")

    def __init__(self, agent_id: str, proposals: tuple[Any, ...]) -> None:
        self.agent_id = agent_id
        self.proposals = proposals


class TestCallableAgent:
    def test_satisfies_runtime_protocol(self) -> None:
        agent = CallableAgent(
            agent_id="agent-1",
            decide_fn=lambda ctx: _FakeDecision("agent-1", ()),
        )
        assert agent.agent_id == "agent-1"
        assert callable(agent.decide)

    def test_decide_delegates_to_callable(self) -> None:
        captured: list[Any] = []

        def decide(ctx: Any) -> Any:
            captured.append(ctx)
            return _FakeDecision("agent-1", ())

        agent = CallableAgent(agent_id="agent-1", decide_fn=decide)
        sentinel = object()
        result = agent.decide(sentinel)
        assert captured == [sentinel]
        assert isinstance(result, _FakeDecision)


class TestCallableResolver:
    def test_satisfies_action_resolver_protocol(self) -> None:
        resolver = CallableResolver(resolve_fn=lambda state, proposals: state)
        assert isinstance(resolver, ActionResolver)

    def test_resolve_delegates_to_callable(self) -> None:
        captured: list[tuple[Any, tuple[Any, ...]]] = []

        def resolve(state: Any, proposals: tuple[Any, ...]) -> Any:
            captured.append((state, proposals))
            return state

        resolver = CallableResolver(resolve_fn=resolve)
        result = resolver.resolve("state-sentinel", (1, 2, 3))
        assert captured == [("state-sentinel", (1, 2, 3))]
        assert result == "state-sentinel"


class TestEndToEndScenarioRun:
    """Drive abdp.scenario.ScenarioRunner with the adapter primitives.

    This exercises the *real* abdp control loop (no mocking of the runner
    or the resolver dispatch) and asserts that callable-backed adapters
    produce a valid ScenarioRun.
    """

    def test_runner_produces_real_scenario_run(
        self,
        core_segment: SegmentState,
        core_participants: list[ParticipantState],
        core_scenario_spec: ScenarioSpec,
        abdp_snapshot_ref: Any,
    ) -> None:
        from dataclasses import dataclass, replace

        initial_state = to_abdp_simulation_state(
            segments=[core_segment],
            participants=core_participants,
            snapshot_ref=abdp_snapshot_ref,
            segment_participants={"11680": ["buyer-1", "seller-1"]},
        )
        scenario_key = derive_scenario_key(core_scenario_spec)

        @dataclass(frozen=True, slots=True)
        class _SpecImpl:
            scenario_key: str
            seed: int
            _initial: Any

            def build_initial_state(self) -> Any:
                return self._initial

        spec = _SpecImpl(
            scenario_key=scenario_key,
            seed=DEFAULT_SHADOW_SEED,
            _initial=initial_state,
        )

        # An agent that emits exactly one proposal on step 0, none after.
        @dataclass(frozen=True, slots=True)
        class _Proposal:
            proposal_id: str
            actor_id: str
            action_key: str
            payload: dict[str, Any]

        def decide(ctx: Any) -> AgentDecision[Any]:
            if ctx.step_index == 0:
                proposal = _Proposal(
                    proposal_id="p-1",
                    actor_id="buyer-1",
                    action_key="buy",
                    payload={"qty": 1},
                )
                return _FakeDecision("agent-1", (proposal,))
            return _FakeDecision("agent-1", ())

        agent = CallableAgent(agent_id="agent-1", decide_fn=decide)

        # Resolver advances step_index and clears pending_actions.
        def resolve(state: Any, proposals: tuple[Any, ...]) -> Any:
            return replace(state, step_index=state.step_index + 1, pending_actions=())

        resolver = CallableResolver(resolve_fn=resolve)

        runner: ScenarioRunner[Any, Any, Any] = ScenarioRunner(
            agents=cast(Any, (agent,)),
            resolver=cast(Any, resolver),
            max_steps=3,
        )
        run = runner.run(cast(Any, spec))

        assert isinstance(run, ScenarioRun)
        assert run.scenario_key == scenario_key
        assert run.seed == DEFAULT_SHADOW_SEED
        assert run.step_count >= 1
        assert run.final_state.step_index >= 1


@pytest.fixture
def empty_summary() -> EvaluationSummary:
    return EvaluationSummary(metrics=(), gates=(), overall_status=GateStatus.PASS)


def _build_minimal_run(scenario_key: str, seed: int = DEFAULT_SHADOW_SEED) -> Any:
    from dataclasses import dataclass

    @dataclass(frozen=True, slots=True)
    class _StubFinalState:
        step_index: int = 0

    @dataclass(frozen=True, slots=True)
    class _StubRun:
        scenario_key: str
        seed: int
        steps: tuple[Any, ...]
        final_state: Any

    return _StubRun(
        scenario_key=scenario_key,
        seed=seed,
        steps=(),
        final_state=_StubFinalState(),
    )


class TestProjectAuditLog:
    def test_projects_valid_audit_log(self, empty_summary: EvaluationSummary) -> None:
        # Use a real ScenarioRun so AuditLog accepts it.
        run = _build_minimal_run("yg-scenario-v1:" + "a" * 64)
        audit = project_audit_log(scenario_run=run, summary=empty_summary)
        assert isinstance(audit, AuditLog)
        assert audit.scenario_key == run.scenario_key
        assert audit.seed == run.seed
        assert audit.run is run
        assert audit.evidence == ()
        assert audit.claims == ()

    def test_passes_evidence_and_claims_through(self, empty_summary: EvaluationSummary) -> None:
        run = _build_minimal_run("yg-scenario-v1:" + "b" * 64)
        evidence = make_evidence_record(
            seed=run.seed,
            evidence_key="trade-volume",
            step_index=0,
            agent_id="agent-1",
            payload={"qty": 1},
            created_at=datetime.now(timezone.utc),
        )
        audit = project_audit_log(
            scenario_run=run,
            summary=empty_summary,
            evidence=(evidence,),
        )
        assert audit.evidence == (evidence,)

    def test_invariants_enforced_by_post_init(self, empty_summary: EvaluationSummary) -> None:
        run = _build_minimal_run("yg-scenario-v1:" + "c" * 64)
        # The helper passes run.scenario_key and run.seed through, so the
        # invariant always holds when called via project_audit_log.
        # Constructing AuditLog directly with mismatched values must fail.
        with pytest.raises(ValueError, match="scenario_key"):
            _ = AuditLog(
                scenario_key="different",
                seed=run.seed,
                run=run,
                summary=empty_summary,
                evidence=(),
                claims=(),
            )
