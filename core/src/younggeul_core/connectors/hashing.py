"""Deterministic SHA-256 hashing for data payloads."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def sha256_payload(records: list[dict[str, Any]]) -> str:
    """Compute a deterministic SHA-256 hex digest for a list of record dicts.

    Records are serialized to JSON with sorted keys and no whitespace
    to ensure deterministic output regardless of dict insertion order.

    Args:
        records: List of dictionaries representing raw data rows.

    Returns:
        64-character lowercase hex SHA-256 string.
    """
    canonical = json.dumps(records, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
