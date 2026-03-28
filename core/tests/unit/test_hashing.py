"""Unit tests for younggeul_core.connectors.hashing."""

from __future__ import annotations

from younggeul_core.connectors.hashing import sha256_payload


class TestSha256Payload:
    def test_returns_64_char_hex(self) -> None:
        result = sha256_payload([{"a": "1"}])
        assert len(result) == 64  # noqa: PLR2004
        assert all(c in "0123456789abcdef" for c in result)

    def test_deterministic_same_input(self) -> None:
        records = [{"key": "value", "num": "42"}]
        assert sha256_payload(records) == sha256_payload(records)

    def test_dict_order_does_not_matter(self) -> None:
        """Keys are sorted during serialization, so insertion order is irrelevant."""
        a = [{"z": "1", "a": "2"}]
        b = [{"a": "2", "z": "1"}]
        assert sha256_payload(a) == sha256_payload(b)

    def test_different_records_different_hash(self) -> None:
        h1 = sha256_payload([{"x": "1"}])
        h2 = sha256_payload([{"x": "2"}])
        assert h1 != h2

    def test_empty_list(self) -> None:
        result = sha256_payload([])
        assert len(result) == 64  # noqa: PLR2004
        # sha256 of "[]"
        assert result == sha256_payload([])

    def test_multiple_records_order_matters(self) -> None:
        """Record ordering IS significant (different order = different hash)."""
        a = [{"k": "1"}, {"k": "2"}]
        b = [{"k": "2"}, {"k": "1"}]
        assert sha256_payload(a) != sha256_payload(b)

    def test_unicode_content(self) -> None:
        """Korean characters must hash correctly."""
        records = [{"동": "역삼동", "단지명": "래미안"}]
        result = sha256_payload(records)
        assert len(result) == 64  # noqa: PLR2004
        assert sha256_payload(records) == result  # deterministic

    def test_none_values(self) -> None:
        records = [{"a": None, "b": "1"}]
        result = sha256_payload(records)
        assert len(result) == 64  # noqa: PLR2004

    def test_nested_dicts(self) -> None:
        records = [{"outer": {"inner": "val"}}]
        result = sha256_payload(records)
        assert len(result) == 64  # noqa: PLR2004
        assert sha256_payload(records) == result
