from __future__ import annotations

import pytest

from younggeul_core._compat import ENV_VAR
from younggeul_core.connectors.hashing import sha256_payload

pytest.importorskip("abdp")


PAYLOADS: list[list[dict[str, object]]] = [
    [],
    [{"a": 1}],
    [{"b": 2, "a": 1}, {"c": 3.5, "d": "한글"}],
    [{"nested": {"x": [1, 2, 3], "y": None}}],
    [{f"key_{i}": i for i in range(50)} for _ in range(10)],
]


@pytest.mark.parametrize("payload", PAYLOADS, ids=range(len(PAYLOADS)))
def test_sha256_payload_local_and_abdp_are_byte_identical(
    monkeypatch: pytest.MonkeyPatch, payload: list[dict[str, object]]
) -> None:
    monkeypatch.setenv(ENV_VAR, "local")
    local_hash = sha256_payload(payload)

    monkeypatch.setenv(ENV_VAR, "abdp")
    abdp_hash = sha256_payload(payload)

    assert local_hash == abdp_hash, f"backend mismatch for payload {payload!r}"
    assert len(local_hash) == 64
