"""Factory for creating BronzeIngestManifest instances."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from younggeul_core.state.bronze import BronzeIngestManifest


def build_manifest(
    *,
    source_id: str,
    api_endpoint: str,
    request_params: dict[str, str],
    response_count: int,
    ingested_at: datetime,
    status: Literal["success", "partial", "failed"],
    error_message: str | None = None,
) -> BronzeIngestManifest:
    """Create a BronzeIngestManifest with an auto-generated manifest_id.

    Args:
        source_id: Identifier for the data source (e.g., "molit.apartment.transactions").
        api_endpoint: Name or URL of the API endpoint called.
        request_params: Parameters used in the API request.
        response_count: Number of records returned.
        ingested_at: Timestamp of the ingestion.
        status: Outcome of the ingestion ("success", "partial", "failed").
        error_message: Optional error message if status is not "success".

    Returns:
        A frozen BronzeIngestManifest instance.
    """
    return BronzeIngestManifest(
        manifest_id=str(uuid.uuid4()),
        source_id=source_id,
        api_endpoint=api_endpoint,
        request_params=request_params,
        response_count=response_count,
        ingested_at=ingested_at,
        status=status,
        error_message=error_message,
    )
