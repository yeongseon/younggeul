"""Guardrail tests for the fit-gap forbidden-patterns list.

These tests fail loudly if any code path starts surfacing public IDs
(Seed, scenario_key, snapshot_id UUID, proposal_id, segment IDs) on
the user-facing CLI, or if `younggeul_core._compat` itself starts
re-exporting `abdp.simulation` Protocols (those values may only be
minted runner-internal under the shadow-runner work). See
`docs/architecture/abdp-simulation-fit-gap.md` Section 5 and the final
selective-adoption inventory in ADR-012.
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
    """`younggeul_core._compat` (and the `data`/`reporting` opt-in
    typing surfaces) MUST NOT re-export any abdp.simulation Protocol
    or the SimulationState/SnapshotRef dataclasses. Those carry
    public-ID-bearing fields whose values may only be minted runner-
    internal under the shadow-runner work, never published as
    framework-typed names from the compat layer."""
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
            f"younggeul_core._compat must not expose `{name}` "
            "(see docs/architecture/abdp-simulation-fit-gap.md §5 and "
            "ADR-012 final selective-adoption inventory)"
        )

    for sub in ("data", "reporting"):
        mod = importlib.import_module(f"younggeul_core._compat.{sub}")
        for name in forbidden:
            assert not hasattr(mod, name), (
                f"younggeul_core._compat.{sub} must not expose `{name}` "
                "(see docs/architecture/abdp-simulation-fit-gap.md §5 and "
                "ADR-012 final selective-adoption inventory)"
            )


def test_younggeul_core_state_simulation_does_not_import_abdp_simulation() -> None:
    """`younggeul_core.state.simulation` MUST stay free of any
    `abdp.simulation` import. Per the final selective-adoption
    inventory, this module is intentionally younggeul-owned domain
    schema; routing it through abdp would either pull in Protocol
    types we are forbidden to expose or signal a default flip that
    Oracle's binding 2026-04-23 finalization ruling explicitly rejects."""
    src = (REPO_ROOT / "core" / "src" / "younggeul_core" / "state" / "simulation.py").read_text(encoding="utf-8")
    assert "abdp.simulation" not in src, (
        "state/simulation.py must not import from abdp.simulation "
        "(see docs/architecture/abdp-simulation-fit-gap.md §5 and "
        "ADR-012 final selective-adoption inventory)"
    )
    assert "from abdp" not in src, (
        "state/simulation.py must not import from any abdp.* module "
        "(see docs/architecture/abdp-simulation-fit-gap.md §5 and "
        "ADR-012 final selective-adoption inventory)"
    )


def test_simulate_cli_does_not_expose_seed_flag() -> None:
    """The `simulate` CLI MUST NOT advertise a `--seed` or
    `--scenario-key` flag. Per Oracle's design ruling for the shadow-runner work and the final
    inventory, those identifiers are runner-internal only; publishing
    them as CLI surface would commit to a cross-engine determinism
    contract younggeul does not implement."""
    result = subprocess.run(
        [sys.executable, "-m", "younggeul_app_kr_seoul_apartment.cli", "simulate", "--help"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "--seed" not in result.stdout, (
        "simulate CLI must not expose --seed (see docs/architecture/abdp-simulation-fit-gap.md §5)"
    )
    assert "--scenario-key" not in result.stdout, (
        "simulate CLI must not expose --scenario-key (see docs/architecture/abdp-simulation-fit-gap.md §5)"
    )


def test_default_backend_remains_local() -> None:
    """`younggeul_core._compat.DEFAULT_BACKEND` MUST stay ``'local'``.

    Per the ADR-012 2026-04-23 finalization ruling, there is no
    default flip: the abdp backend is opt-in via
    ``YOUNGGEUL_CORE_BACKEND=abdp``. A future contributor flipping
    this constant must escalate via a new ADR/epic, not a silent edit.
    """
    from younggeul_core._compat import DEFAULT_BACKEND

    assert DEFAULT_BACKEND == "local", (
        "DEFAULT_BACKEND must remain 'local' per the ADR-012 2026-04-23 finalization ruling. "
        "A default flip requires a new ADR/epic, not a constant rename."
    )
