"""Unit tests for younggeul_core.connectors.manifest."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from younggeul_core.connectors.manifest import build_manifest
from younggeul_core.state.bronze import BronzeIngestManifest


def _base_params() -> dict[str, object]:
    return {
        "source_id": "molit.apartment.transactions",
        "api_endpoint": "getRTMSDataSvcAptTradeDev",
        "request_params": {"sigungu_code": "11650", "year_month": "202301"},
        "response_count": 150,
        "ingested_at": datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
        "status": "success",
    }


class TestBuildManifest:
    def test_returns_bronze_ingest_manifest(self) -> None:
        result = build_manifest(**_base_params())  # type: ignore[arg-type]
        assert isinstance(result, BronzeIngestManifest)

    def test_manifest_id_is_uuid(self) -> None:
        import uuid

        result = build_manifest(**_base_params())  # type: ignore[arg-type]
        # Should be a valid UUID4 string
        parsed = uuid.UUID(result.manifest_id)
        assert parsed.version == 4  # noqa: PLR2004

    def test_manifest_id_unique_per_call(self) -> None:
        m1 = build_manifest(**_base_params())  # type: ignore[arg-type]
        m2 = build_manifest(**_base_params())  # type: ignore[arg-type]
        assert m1.manifest_id != m2.manifest_id

    def test_fields_match_input(self) -> None:
        params = _base_params()
        result = build_manifest(**params)  # type: ignore[arg-type]
        assert result.source_id == params["source_id"]
        assert result.api_endpoint == params["api_endpoint"]
        assert result.request_params == params["request_params"]
        assert result.response_count == params["response_count"]
        assert result.ingested_at == params["ingested_at"]
        assert result.status == params["status"]
        assert result.error_message is None

    def test_error_message_set(self) -> None:
        params = _base_params()
        params["status"] = "failed"
        params["error_message"] = "API returned 500"
        result = build_manifest(**params)  # type: ignore[arg-type]
        assert result.status == "failed"
        assert result.error_message == "API returned 500"

    def test_partial_status(self) -> None:
        params = _base_params()
        params["status"] = "partial"
        params["response_count"] = 50
        result = build_manifest(**params)  # type: ignore[arg-type]
        assert result.status == "partial"
        assert result.response_count == 50  # noqa: PLR2004

    def test_manifest_is_frozen(self) -> None:
        result = build_manifest(**_base_params())  # type: ignore[arg-type]
        with pytest.raises(Exception):  # noqa: B017 — Pydantic raises ValidationError on frozen
            result.source_id = "changed"  # type: ignore[misc]

    def test_zero_response_count(self) -> None:
        params = _base_params()
        params["response_count"] = 0
        result = build_manifest(**params)  # type: ignore[arg-type]
        assert result.response_count == 0
