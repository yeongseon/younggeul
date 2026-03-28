"""younggeul_core.connectors — shared connector primitives for data ingestion."""

from younggeul_core.connectors.hashing import sha256_payload
from younggeul_core.connectors.manifest import build_manifest
from younggeul_core.connectors.protocol import Connector, ConnectorResult
from younggeul_core.connectors.rate_limit import RateLimiter
from younggeul_core.connectors.retry import ConnectorError, NonRetryableError, retry

__all__ = [
    "Connector",
    "ConnectorError",
    "ConnectorResult",
    "NonRetryableError",
    "RateLimiter",
    "build_manifest",
    "retry",
    "sha256_payload",
]
