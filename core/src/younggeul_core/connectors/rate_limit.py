"""Simple per-connector rate limiter."""

from __future__ import annotations

import time


class RateLimiter:
    """Token-bucket-style rate limiter that enforces a minimum interval between calls.

    Thread-safe for single-threaded async or synchronous usage.
    For v0.1, this is a simple blocking limiter.

    Args:
        min_interval: Minimum seconds between consecutive calls.
    """

    def __init__(self, min_interval: float = 1.0) -> None:
        if min_interval < 0:
            msg = f"min_interval must be non-negative, got {min_interval}"
            raise ValueError(msg)
        self._min_interval = min_interval
        self._last_call: float = 0.0

    @property
    def min_interval(self) -> float:
        """Return the configured minimum interval in seconds."""
        return self._min_interval

    def wait(self) -> None:
        """Block until the minimum interval has elapsed since the last call."""
        if self._min_interval <= 0:
            return

        now = time.monotonic()
        elapsed = now - self._last_call
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)

        self._last_call = time.monotonic()

    def reset(self) -> None:
        """Reset the limiter, allowing the next call immediately."""
        self._last_call = 0.0
