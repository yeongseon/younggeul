"""ID derivation and ScenarioContract normalization for the
abdp shadow runner adapter (see ADR-012 + docs/architecture/abdp-simulation-fit-gap.md).

These helpers exist so the scenario-adapter slice can produce a real
`abdp.scenario.ScenarioRun` whose `scenario_key`, `seed`, and
`SnapshotRef.snapshot_id` carry deterministic, internal-only values
derived from younggeul's existing canonical sources (sha256 snapshot
digests; ScenarioSpec contract). Per the Oracle ruling on 2026-04-23:

  * `Seed` is reserved for future RNG-bearing simulation work; today it
    is a constant `0`. It is NOT derived from any user-facing identity,
    and there is no `--seed` CLI flag.
  * `scenario_key` is a versioned full-hash of a normalized
    `ScenarioContract v1`, NOT the field shape of `ScenarioSpec`. It is
    not truncated; the full sha256 hex is preserved.
  * `snapshot_uuid` is generated via `uuid5(YOUNGGEUL_SNAPSHOT_NAMESPACE,
    sha256_hex)` and paired with an explicit per-run lookup map so the
    sha256 content-address (younggeul's source of truth) is recoverable
    at any adapter boundary. UUID is never canonical outside this layer.

All three values are runner-internal: never logged in markdown reports,
never surfaced in CLI text, never persisted as primary keys in
younggeul-owned storage. They appear only inside abdp `ScenarioRun` /
`AuditLog` / abdp JSON artifacts.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from younggeul_core.state.simulation import ScenarioSpec

SCENARIO_KEY_VERSION: Final[str] = "yg-scenario-v1"

YOUNGGEUL_SNAPSHOT_NAMESPACE: Final[uuid.UUID] = uuid.UUID("8b2d6b06-6f4f-5b0a-9f2e-abc123450001")
"""Stable UUID5 namespace for projecting younggeul sha256 snapshot
digests to abdp `SnapshotRef.snapshot_id` UUIDs. Generated once and
frozen here; rotating it would invalidate every previously generated
`snapshot_uuid` and is therefore forbidden without a new
`SCENARIO_KEY_VERSION`-style versioning scheme."""

DEFAULT_SHADOW_SEED: Final[int] = 0
"""Seed value used by the shadow-runner `ScenarioRun`. younggeul has no
RNG-seeded simulation behavior today, so the seed has no entropy role
and is a constant. If randomness is later introduced, the seed must
become an explicit cross-engine input before any parity claim
continues; do not silently lift a non-zero default here."""


def normalize_scenario_contract(spec: ScenarioSpec) -> dict[str, Any]:
    """Project a younggeul `ScenarioSpec` into the canonical, sortable
    `ScenarioContract v1` mapping the `scenario_key` is hashed from.

    The mapping is deliberately a small, versioned shape distinct from
    `ScenarioSpec` itself so future field additions to `ScenarioSpec`
    do not silently change `scenario_key` for unrelated reasons.
    """
    return {
        "version": 1,
        "scenario_name": spec.scenario_name,
        "target_gus": sorted(spec.target_gus),
        "target_period_start": spec.target_period_start.isoformat(),
        "target_period_end": spec.target_period_end.isoformat(),
        "shocks": sorted(
            (
                {
                    "shock_type": s.shock_type,
                    "description": s.description,
                    "magnitude": s.magnitude,
                    "target_segments": sorted(s.target_segments),
                }
                for s in spec.shocks
            ),
            key=lambda d: (d["shock_type"], d["description"], d["magnitude"]),
        ),
    }


def derive_scenario_key(spec: ScenarioSpec) -> str:
    """Derive a deterministic, versioned `scenario_key` for the shadow
    `ScenarioRun`. Stable across re-runs of the same scenario contract;
    sensitive to roster/shock changes via `normalize_scenario_contract`.

    Returns a string of shape ``"yg-scenario-v1:<sha256hex>"``. Full
    digest is preserved (no truncation) per Oracle's design ruling.
    """
    contract = normalize_scenario_contract(spec)
    payload = json.dumps(contract, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    return f"{SCENARIO_KEY_VERSION}:{digest}"


def derive_snapshot_uuid(sha256_hex: str) -> uuid.UUID:
    """Project a younggeul sha256 snapshot digest to an abdp
    `SnapshotRef.snapshot_id` UUID via `uuid5` over a frozen namespace.

    `uuid5` is deterministic and one-way; pair it with a
    `SnapshotIdRegistry` (below) to recover the original sha256 hex
    when projecting back at the adapter boundary.
    """
    if not isinstance(sha256_hex, str) or len(sha256_hex) != 64:
        raise ValueError(
            f"sha256_hex must be a 64-char hex digest; got {len(sha256_hex) if isinstance(sha256_hex, str) else type(sha256_hex).__name__}"
        )
    try:
        int(sha256_hex, 16)
    except ValueError as exc:
        raise ValueError(f"sha256_hex must be hex-only; got non-hex characters in {sha256_hex!r}") from exc
    return uuid.uuid5(YOUNGGEUL_SNAPSHOT_NAMESPACE, sha256_hex.lower())


class SnapshotIdRegistry:
    """Per-run bijection between younggeul sha256 snapshot digests and
    the abdp `SnapshotRef.snapshot_id` UUIDs derived from them.

    Populated at adapter creation time; consulted whenever the adapter
    projects an abdp `SnapshotRef` back to a younggeul sha256
    content-address. Without this map, the `uuid5` projection alone is
    not invertible.
    """

    __slots__ = ("_uuid_to_sha", "_sha_to_uuid")

    def __init__(self) -> None:
        self._uuid_to_sha: dict[uuid.UUID, str] = {}
        self._sha_to_uuid: dict[str, uuid.UUID] = {}

    def register(self, sha256_hex: str) -> uuid.UUID:
        """Idempotently register a sha256 digest and return its UUID."""
        normalized = sha256_hex.lower()
        existing = self._sha_to_uuid.get(normalized)
        if existing is not None:
            return existing
        snapshot_uuid = derive_snapshot_uuid(normalized)
        self._sha_to_uuid[normalized] = snapshot_uuid
        self._uuid_to_sha[snapshot_uuid] = normalized
        return snapshot_uuid

    def sha256_for(self, snapshot_uuid: uuid.UUID) -> str:
        """Recover the sha256 digest for a previously registered UUID."""
        try:
            return self._uuid_to_sha[snapshot_uuid]
        except KeyError as exc:
            raise KeyError(
                f"snapshot_uuid {snapshot_uuid} is not registered; the abdp "
                "adapter must register every sha256 digest it projects"
            ) from exc

    def __contains__(self, key: object) -> bool:
        if isinstance(key, uuid.UUID):
            return key in self._uuid_to_sha
        if isinstance(key, str):
            return key.lower() in self._sha_to_uuid
        return False

    def __len__(self) -> int:
        return len(self._uuid_to_sha)


__all__ = [
    "DEFAULT_SHADOW_SEED",
    "SCENARIO_KEY_VERSION",
    "SnapshotIdRegistry",
    "YOUNGGEUL_SNAPSHOT_NAMESPACE",
    "derive_scenario_key",
    "derive_snapshot_uuid",
    "normalize_scenario_contract",
]
