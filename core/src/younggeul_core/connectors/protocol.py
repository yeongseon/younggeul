"""Connector protocol and result types for data ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Generic, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

from younggeul_core.state.bronze import BronzeIngestManifest

TReq = TypeVar("TReq", contravariant=True)
TRec = TypeVar("TRec", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class ConnectorResult(Generic[TRec]):
    """Immutable result of a single connector fetch operation.

    Each result corresponds to one logical partition (e.g., one month + one district).
    """

    records: list[TRec]
    manifest: BronzeIngestManifest


@runtime_checkable
class Connector(Protocol[TReq, TRec]):
    """Protocol that all data connectors must satisfy.

    Type Parameters:
        TReq: The request model type (defines what to fetch).
        TRec: The Bronze record model type (defines what is returned).
    """

    source_id: ClassVar[str]

    def fetch(self, request: TReq) -> ConnectorResult[TRec]:
        """Fetch data for a single partition and return typed Bronze records.

        Args:
            request: Partition-scoped request parameters.

        Returns:
            ConnectorResult containing records and an ingest manifest.

        Raises:
            ConnectorError: On unrecoverable fetch or mapping failures.
        """
        ...
