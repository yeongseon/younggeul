"""Unit tests for younggeul_core.connectors.rate_limit."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from younggeul_core.connectors.rate_limit import RateLimiter


class TestRateLimiterInit:
    def test_default_interval(self) -> None:
        limiter = RateLimiter()
        assert limiter.min_interval == 1.0  # noqa: PLR2004

    def test_custom_interval(self) -> None:
        limiter = RateLimiter(min_interval=0.5)
        assert limiter.min_interval == 0.5  # noqa: PLR2004

    def test_zero_interval(self) -> None:
        limiter = RateLimiter(min_interval=0.0)
        assert limiter.min_interval == 0.0

    def test_negative_interval_raises(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            RateLimiter(min_interval=-1.0)


class TestRateLimiterWait:
    @patch("younggeul_core.connectors.rate_limit.time.sleep")
    @patch("younggeul_core.connectors.rate_limit.time.monotonic")
    def test_first_call_no_sleep(self, mock_monotonic: object, mock_sleep: object) -> None:
        """First call should not sleep (last_call is 0.0, monotonic > 0)."""
        from unittest.mock import MagicMock

        mock_monotonic = mock_monotonic  # type: ignore[assignment]
        mock_sleep = mock_sleep  # type: ignore[assignment]
        assert isinstance(mock_monotonic, MagicMock)
        assert isinstance(mock_sleep, MagicMock)

        mock_monotonic.return_value = 100.0
        limiter = RateLimiter(min_interval=1.0)
        limiter.wait()
        mock_sleep.assert_not_called()

    @patch("younggeul_core.connectors.rate_limit.time.sleep")
    @patch("younggeul_core.connectors.rate_limit.time.monotonic")
    def test_second_call_sleeps_if_too_soon(self, mock_monotonic: object, mock_sleep: object) -> None:
        from unittest.mock import MagicMock

        mock_monotonic = mock_monotonic  # type: ignore[assignment]
        mock_sleep = mock_sleep  # type: ignore[assignment]
        assert isinstance(mock_monotonic, MagicMock)
        assert isinstance(mock_sleep, MagicMock)

        # First call at t=100, second call at t=100.3 (only 0.3s elapsed)
        mock_monotonic.side_effect = [100.0, 100.0, 100.3, 100.3]
        limiter = RateLimiter(min_interval=1.0)
        limiter.wait()  # first call: no sleep
        limiter.wait()  # second call: should sleep 0.7s
        mock_sleep.assert_called_once()
        sleep_duration = mock_sleep.call_args[0][0]
        assert sleep_duration == pytest.approx(0.7, abs=0.01)

    def test_zero_interval_never_sleeps(self) -> None:
        limiter = RateLimiter(min_interval=0.0)
        # Should complete without delay
        for _ in range(10):
            limiter.wait()


class TestRateLimiterReset:
    @patch("younggeul_core.connectors.rate_limit.time.sleep")
    @patch("younggeul_core.connectors.rate_limit.time.monotonic")
    def test_reset_allows_immediate_call(self, mock_monotonic: object, mock_sleep: object) -> None:
        from unittest.mock import MagicMock

        mock_monotonic = mock_monotonic  # type: ignore[assignment]
        mock_sleep = mock_sleep  # type: ignore[assignment]
        assert isinstance(mock_monotonic, MagicMock)
        assert isinstance(mock_sleep, MagicMock)

        # First call at t=100, reset, then second call at t=100.1
        mock_monotonic.side_effect = [100.0, 100.0, 100.1, 100.1]
        limiter = RateLimiter(min_interval=1.0)
        limiter.wait()
        limiter.reset()
        limiter.wait()  # After reset, should not sleep
        mock_sleep.assert_not_called()
