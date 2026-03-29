"""Retry logic with exponential backoff and jitter for connector operations."""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Errors that should NOT be retried.
_NON_RETRYABLE_STATUS_CODES = frozenset({400, 401, 403, 404, 405})


class ConnectorError(Exception):
    """Base exception for connector failures."""

    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


class NonRetryableError(ConnectorError):
    """Error that should not be retried (auth, bad params, mapping bugs)."""

    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=False)


def retry(
    fn: Callable[[], T],
    *,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    jitter: float = 0.5,
) -> T:
    """Execute a function with exponential backoff retry.

    Retries on ConnectorError with retryable=True, OSError (network),
    and TimeoutError. Does NOT retry NonRetryableError or unexpected exceptions.

    Args:
        fn: Zero-argument callable to execute.
        max_attempts: Total number of attempts (including the first).
        base_delay: Initial delay in seconds before first retry.
        max_delay: Maximum delay cap in seconds.
        jitter: Maximum random jitter added to delay (fraction of delay).

    Returns:
        The return value of fn on success.

    Raises:
        ConnectorError: After exhausting all retry attempts.
        NonRetryableError: Immediately on non-retryable errors.
    """
    last_exception: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except NonRetryableError:
            raise
        except ConnectorError as exc:
            if not exc.retryable:
                raise
            last_exception = exc
        except (OSError, TimeoutError) as exc:
            last_exception = exc
        except Exception:
            raise

        if attempt < max_attempts:
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            delay += random.uniform(0, delay * jitter)  # noqa: S311
            logger.warning(
                "Attempt %d/%d failed: %s. Retrying in %.1fs...",
                attempt,
                max_attempts,
                last_exception,
                delay,
            )
            time.sleep(delay)

    assert last_exception is not None  # noqa: S101
    raise last_exception
