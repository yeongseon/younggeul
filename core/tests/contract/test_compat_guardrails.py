"""Guardrail tests for the M7' fit-gap forbidden-patterns list.

These tests fail loudly if any pre-M9' code path starts synthesizing
public IDs (Seed, scenario_key, snapshot_id UUID, proposal_id, segment
IDs) or re-exporting `abdp.simulation` Protocols. See
`docs/architecture/abdp-simulation-fit-gap.md` Section 5.
"""

from __future__ import annotations

import importlib
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_compat_does_not_export_abdp_simulation_protocols() -> None:
    """`younggeul_core._compat` MUST NOT re-export any abdp.simulation Protocol
    or the SimulationState/SnapshotRef dataclasses. All of those carry
    public-ID-bearing fields whose values can only be minted under the M9'
    shadow ScenarioRunner with real provenance."""
    forbidden = {
        "ScenarioSpec",
        "SegmentState",
        "ParticipantState",
        "ActionProposal",
        "SnapshotRef",
        "SimulationState",
        "Seed",
    }

    if importlib.util.find_spec("abdp") is None:
        pytest.skip("abdp not installed")

    compat = importlib.import_module("younggeul_core._compat")
    for name in forbidden:
        assert not hasattr(compat, name), (
            f"younggeul_core._compat must not expose `{name}` pre-M9' "
            "(see docs/architecture/abdp-simulation-fit-gap.md §5)"
        )

    for sub in ("data", "reporting"):
        mod = importlib.import_module(f"younggeul_core._compat.{sub}")
        for name in forbidden:
            assert not hasattr(mod, name), (
                f"younggeul_core._compat.{sub} must not expose `{name}` pre-M9' "
                "(see docs/architecture/abdp-simulation-fit-gap.md §5)"
            )


def test_younggeul_core_state_simulation_does_not_import_abdp_simulation() -> None:
    """`younggeul_core.state.simulation` MUST stay free of any
    `abdp.simulation` import until M9'. Importing it would either pull
    in Protocol types we are forbidden to expose or signal an in-progress
    swap that bypasses the gating."""
    src = (REPO_ROOT / "core" / "src" / "younggeul_core" / "state" / "simulation.py").read_text(encoding="utf-8")
    assert "abdp.simulation" not in src, (
        "state/simulation.py must not import from abdp.simulation pre-M9' "
        "(see docs/architecture/abdp-simulation-fit-gap.md §5)"
    )
    assert "from abdp" not in src, (
        "state/simulation.py must not import from any abdp.* module pre-M9' "
        "(see docs/architecture/abdp-simulation-fit-gap.md §5)"
    )


def test_simulate_cli_does_not_expose_seed_flag() -> None:
    """The `simulate` CLI MUST NOT advertise a `--seed` flag pre-M9'.
    Adding one would publish a cross-engine determinism contract we do
    not yet implement (see fit-gap §2 hard constraints, item 2)."""
    result = subprocess.run(
        [sys.executable, "-m", "younggeul_app_kr_seoul_apartment.cli", "simulate", "--help"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "--seed" not in result.stdout, (
        "simulate CLI must not expose --seed pre-M9' (see docs/architecture/abdp-simulation-fit-gap.md §5)"
    )
    assert "--scenario-key" not in result.stdout, (
        "simulate CLI must not expose --scenario-key pre-M9' (see docs/architecture/abdp-simulation-fit-gap.md §5)"
    )
