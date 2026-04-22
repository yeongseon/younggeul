"""Deterministic SHA-256 hashing for data payloads.

When ``YOUNGGEUL_CORE_BACKEND=abdp`` (see ADR-012), the hashing is
delegated to ``abdp.core.stable_hash``, which produces byte-identical
output to the local implementation (verified by the parity contract
test ``core/tests/contract/test_compat_hashing_parity.py``).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, cast

from younggeul_core._compat import get_backend


def sha256_payload(records: list[dict[str, Any]]) -> str:
    """Compute a deterministic SHA-256 hex digest for a list of record dicts.

    Records are serialized to JSON with sorted keys and no whitespace
    to ensure deterministic output regardless of dict insertion order.

    Args:
        records: List of dictionaries representing raw data rows.

    Returns:
        64-character lowercase hex SHA-256 string.
    """
    if get_backend() == "abdp":
        from abdp.core import JsonValue, stable_hash

        return str(stable_hash(cast("JsonValue", records)))
    canonical = json.dumps(records, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
