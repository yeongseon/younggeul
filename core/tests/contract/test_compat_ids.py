"""Contract tests for `_compat.ids`.

Verifies the deterministic ID-derivation contract that the scenario-adapter
slice will rely on. Per the Oracle ruling on 2026-04-23 and
the simulation fit-gap doc:

  * `derive_scenario_key` is a versioned full-hash of a normalized
    `ScenarioContract v1` — stable across re-runs of the same contract,
    sensitive to roster/shock changes, never truncated.
  * `derive_snapshot_uuid` is `uuid5(NAMESPACE, sha256_hex)` — one-way,
    deterministic, paired with `SnapshotIdRegistry` for recovery.
  * `DEFAULT_SHADOW_SEED == 0` — reserved for future RNG work; today a
    constant with no entropy role.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

import pytest

from younggeul_core._compat.ids import (
    DEFAULT_SHADOW_SEED,
    SCENARIO_KEY_VERSION,
    SnapshotIdRegistry,
    YOUNGGEUL_SNAPSHOT_NAMESPACE,
    derive_scenario_key,
    derive_snapshot_uuid,
    normalize_scenario_contract,
)
from younggeul_core.state.simulation import ScenarioSpec, Shock


def _spec(**overrides: Any) -> ScenarioSpec:
    base: dict[str, Any] = {
        "scenario_name": "test",
        "target_gus": ["11680", "11440"],
        "target_period_start": date(2025, 3, 1),
        "target_period_end": date(2025, 6, 1),
        "shocks": [],
    }
    base.update(overrides)
    return ScenarioSpec(**base)


class TestSeed:
    def test_default_shadow_seed_is_zero(self) -> None:
        """Today's seed has no entropy role; constant 0 prevents any
        accidental claim of cross-engine RNG determinism."""
        assert DEFAULT_SHADOW_SEED == 0
        assert isinstance(DEFAULT_SHADOW_SEED, int)


class TestNormalizeScenarioContract:
    def test_target_gus_are_sorted(self) -> None:
        """Re-ordering input gus must not change the contract — the
        contract shape, not the ScenarioSpec field order, is what the
        scenario_key hashes."""
        a = normalize_scenario_contract(_spec(target_gus=["11680", "11440"]))
        b = normalize_scenario_contract(_spec(target_gus=["11440", "11680"]))
        assert a == b
        assert a["target_gus"] == ["11440", "11680"]

    def test_versioned(self) -> None:
        contract = normalize_scenario_contract(_spec())
        assert contract["version"] == 1

    def test_dates_are_isoformat(self) -> None:
        contract = normalize_scenario_contract(_spec())
        assert contract["target_period_start"] == "2025-03-01"
        assert contract["target_period_end"] == "2025-06-01"

    def test_shocks_are_sorted_and_normalized(self) -> None:
        s1 = Shock(
            shock_type="interest_rate",
            description="rate hike",
            magnitude=0.5,
            target_segments=["a", "b"],
        )
        s2 = Shock(
            shock_type="demand",
            description="supply cut",
            magnitude=-0.3,
            target_segments=["c"],
        )
        a = normalize_scenario_contract(_spec(shocks=[s1, s2]))
        b = normalize_scenario_contract(_spec(shocks=[s2, s1]))
        assert a == b
        assert [s["shock_type"] for s in a["shocks"]] == ["demand", "interest_rate"]


class TestDeriveScenarioKey:
    def test_format_is_versioned_full_hash(self) -> None:
        """Per Oracle: scenario_key MUST NOT be truncated. Format is
        ``yg-scenario-v1:<sha256hex>`` with a 64-char hex digest."""
        key = derive_scenario_key(_spec())
        prefix, _, digest = key.partition(":")
        assert prefix == SCENARIO_KEY_VERSION == "yg-scenario-v1"
        assert len(digest) == 64
        assert int(digest, 16) >= 0

    def test_deterministic_across_field_order(self) -> None:
        a = derive_scenario_key(_spec(target_gus=["11680", "11440"]))
        b = derive_scenario_key(_spec(target_gus=["11440", "11680"]))
        assert a == b

    def test_sensitive_to_scenario_name(self) -> None:
        a = derive_scenario_key(_spec(scenario_name="alpha"))
        b = derive_scenario_key(_spec(scenario_name="beta"))
        assert a != b

    def test_sensitive_to_period(self) -> None:
        a = derive_scenario_key(_spec(target_period_end=date(2025, 6, 1)))
        b = derive_scenario_key(_spec(target_period_end=date(2025, 7, 1)))
        assert a != b

    def test_sensitive_to_shocks(self) -> None:
        no_shock = derive_scenario_key(_spec())
        with_shock = derive_scenario_key(
            _spec(
                shocks=[
                    Shock(
                        shock_type="interest_rate",
                        description="d",
                        magnitude=0.1,
                        target_segments=[],
                    )
                ]
            )
        )
        assert no_shock != with_shock


class TestDeriveSnapshotUuid:
    def test_namespace_is_frozen(self) -> None:
        """Rotating the namespace would invalidate every previously
        derived snapshot_uuid; freeze the literal here."""
        assert YOUNGGEUL_SNAPSHOT_NAMESPACE == uuid.UUID("8b2d6b06-6f4f-5b0a-9f2e-abc123450001")

    def test_is_uuid5(self) -> None:
        sha = "a" * 64
        u = derive_snapshot_uuid(sha)
        assert u == uuid.uuid5(YOUNGGEUL_SNAPSHOT_NAMESPACE, sha)
        assert u.version == 5

    def test_deterministic(self) -> None:
        sha = "0123456789abcdef" * 4
        assert derive_snapshot_uuid(sha) == derive_snapshot_uuid(sha)

    def test_case_insensitive(self) -> None:
        assert derive_snapshot_uuid("ABCDEF" + "0" * 58) == derive_snapshot_uuid("abcdef" + "0" * 58)

    def test_distinct_inputs_distinct_uuids(self) -> None:
        assert derive_snapshot_uuid("a" * 64) != derive_snapshot_uuid("b" * 64)

    @pytest.mark.parametrize("bad", ["", "abc", "z" * 64, "a" * 63, "a" * 65])
    def test_rejects_non_sha256_input(self, bad: str) -> None:
        with pytest.raises((ValueError, TypeError)):
            derive_snapshot_uuid(bad)


class TestSnapshotIdRegistry:
    def test_register_returns_derived_uuid(self) -> None:
        reg = SnapshotIdRegistry()
        sha = "a" * 64
        u = reg.register(sha)
        assert u == derive_snapshot_uuid(sha)

    def test_register_is_idempotent(self) -> None:
        reg = SnapshotIdRegistry()
        sha = "a" * 64
        assert reg.register(sha) == reg.register(sha)
        assert len(reg) == 1

    def test_round_trip_uuid_to_sha(self) -> None:
        reg = SnapshotIdRegistry()
        sha = "abcdef0123456789" * 4
        u = reg.register(sha)
        assert reg.sha256_for(u) == sha

    def test_unregistered_uuid_raises(self) -> None:
        reg = SnapshotIdRegistry()
        with pytest.raises(KeyError, match="not registered"):
            reg.sha256_for(uuid.uuid4())

    def test_contains(self) -> None:
        reg = SnapshotIdRegistry()
        sha = "a" * 64
        u = reg.register(sha)
        assert sha in reg
        assert sha.upper() in reg
        assert u in reg
        assert "missing" not in reg
        assert uuid.uuid4() not in reg
        assert 42 not in reg

    def test_two_distinct_snapshots(self) -> None:
        reg = SnapshotIdRegistry()
        u1 = reg.register("a" * 64)
        u2 = reg.register("b" * 64)
        assert u1 != u2
        assert reg.sha256_for(u1) != reg.sha256_for(u2)
        assert len(reg) == 2
