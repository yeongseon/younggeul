from __future__ import annotations

import importlib

import pytest

pytest.importorskip("abdp")


def test_compat_data_reexports_abdp_protocols() -> None:
    mod = importlib.import_module("younggeul_core._compat.data")

    from abdp.data import (
        BronzeContract,
        GoldContract,
        SilverContract,
        SnapshotManifest as AbdpSnapshotManifest,
        SnapshotTier,
    )

    assert mod.BronzeContract is BronzeContract
    assert mod.SilverContract is SilverContract
    assert mod.GoldContract is GoldContract
    assert mod.SnapshotTier is SnapshotTier
    assert mod.AbdpSnapshotManifest is AbdpSnapshotManifest


def test_compat_data_aliases_are_not_local_snapshot_manifest() -> None:
    """Guardrail: the abdp re-export must NOT be conflated with the local
    dataset-level SnapshotManifest in storage.snapshot. Different concept."""
    mod = importlib.import_module("younggeul_core._compat.data")
    from younggeul_core.storage.snapshot import SnapshotManifest as LocalSnapshotManifest

    assert mod.AbdpSnapshotManifest is not LocalSnapshotManifest


def test_compat_data_unknown_attribute_raises() -> None:
    mod = importlib.import_module("younggeul_core._compat.data")
    with pytest.raises(AttributeError, match="has no attribute"):
        _ = mod.DoesNotExist  # type: ignore[attr-defined]
