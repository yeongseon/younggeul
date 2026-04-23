"""Opt-in re-exports of abdp framework data Protocols (see ADR-012).

This module deliberately does **not** replace any younggeul row schema or
the dataset-level ``younggeul_core.storage.snapshot.SnapshotManifest``.
Per the selective-adoption plan (ADR-012 amendment) recorded in ADR-012:

- ``abdp.data.{Bronze,Silver,Gold}Contract`` are abstract structural
  ``Protocol`` types with only ``manifest`` and ``rows`` properties.
- ``younggeul_core.state.{bronze,silver,gold}`` are concrete Pydantic
  schemas for the Korean apartment domain (kpubdata/MOLIT/BOK/KOSTAT).
- ``abdp.data.SnapshotManifest`` is a per-tier UUID-keyed dataclass with
  parent-pointer lineage.
- ``younggeul_core.storage.snapshot.SnapshotManifest`` is a Pydantic
  multi-table dataset manifest with sha256-derived integrity IDs.

These are *not* bijective. We expose abdp's framework contracts here as
an intentional public typing surface for downstream code that wants to
type-annotate "any framework artifact" (e.g., the shadow-runner work
adapter primitives in :mod:`younggeul_core._compat.scenario`). Importing
names from this module pulls in ``abdp`` lazily; code that does not need
framework contracts pays no import cost.

Use of these aliases does **not** imply that the local types satisfy
them — the local types intentionally hold richer state.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from younggeul_core._compat import require_abdp

if TYPE_CHECKING:  # pragma: no cover - typing only
    from abdp.data import (
        BronzeContract,
        GoldContract,
        SilverContract,
        SnapshotManifest as AbdpSnapshotManifest,
        SnapshotTier,
    )


def _resolve() -> tuple[object, object, object, object, object]:
    require_abdp()
    from abdp.data import (
        BronzeContract,
        GoldContract,
        SilverContract,
        SnapshotManifest as AbdpSnapshotManifest,
        SnapshotTier,
    )

    return BronzeContract, SilverContract, GoldContract, SnapshotTier, AbdpSnapshotManifest


def __getattr__(name: str) -> object:
    if name in {
        "BronzeContract",
        "SilverContract",
        "GoldContract",
        "SnapshotTier",
        "AbdpSnapshotManifest",
    }:
        bronze, silver, gold, tier, manifest = _resolve()
        mapping = {
            "BronzeContract": bronze,
            "SilverContract": silver,
            "GoldContract": gold,
            "SnapshotTier": tier,
            "AbdpSnapshotManifest": manifest,
        }
        return mapping[name]
    raise AttributeError(f"module 'younggeul_core._compat.data' has no attribute {name!r}")


__all__ = [
    "AbdpSnapshotManifest",
    "BronzeContract",
    "GoldContract",
    "SilverContract",
    "SnapshotTier",
]
