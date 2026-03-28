"""Unit tests for younggeul_core.connectors.retry."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from younggeul_core.connectors.retry import (
    ConnectorError,
    NonRetryableError,
    retry,
)


class TestConnectorError:
    def test_retryable_by_default(self) -> None:
        exc = ConnectorError("boom")
        assert exc.retryable is True
        assert str(exc) == "boom"

    def test_retryable_false(self) -> None:
        exc = ConnectorError("bad request", retryable=False)
        assert exc.retryable is False

    def test_is_exception(self) -> None:
        assert issubclass(ConnectorError, Exception)


class TestNonRetryableError:
    def test_retryable_always_false(self) -> None:
        exc = NonRetryableError("auth failed")
        assert exc.retryable is False
        assert str(exc) == "auth failed"

    def test_is_connector_error(self) -> None:
        assert issubclass(NonRetryableError, ConnectorError)


class TestRetry:
    def test_success_on_first_attempt(self) -> None:
        result = retry(lambda: 42)
        assert result == 42

    def test_success_after_transient_failure(self) -> None:
        call_count = 0

        def flaky() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectorError("transient")
            return "ok"

        with patch.object(time, "sleep"):
            result = retry(flaky, max_attempts=3, base_delay=0.1)
        assert result == "ok"
        assert call_count == 3

    def test_exhausts_all_attempts(self) -> None:
        def always_fail() -> None:
            raise ConnectorError("always fails")

        with patch.object(time, "sleep"):
            with pytest.raises(ConnectorError, match="always fails"):
                retry(always_fail, max_attempts=3, base_delay=0.01)

    def test_non_retryable_error_raises_immediately(self) -> None:
        call_count = 0

        def bad_auth() -> None:
            nonlocal call_count
            call_count += 1
            raise NonRetryableError("invalid API key")

        with patch.object(time, "sleep"):
            with pytest.raises(NonRetryableError, match="invalid API key"):
                retry(bad_auth, max_attempts=3, base_delay=0.01)

        assert call_count == 1  # No retries for non-retryable

    def test_connector_error_with_retryable_false_raises_immediately(self) -> None:
        call_count = 0

        def bad_params() -> None:
            nonlocal call_count
            call_count += 1
            raise ConnectorError("bad params", retryable=False)

        with patch.object(time, "sleep"):
            with pytest.raises(ConnectorError, match="bad params"):
                retry(bad_params, max_attempts=3, base_delay=0.01)

        assert call_count == 1

    def test_os_error_is_retried(self) -> None:
        call_count = 0

        def network_flaky() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise OSError("connection reset")
            return "recovered"

        with patch.object(time, "sleep"):
            result = retry(network_flaky, max_attempts=3, base_delay=0.01)
        assert result == "recovered"
        assert call_count == 2

    def test_timeout_error_is_retried(self) -> None:
        call_count = 0

        def timeout_flaky() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise TimeoutError("read timed out")
            return "recovered"

        with patch.object(time, "sleep"):
            result = retry(timeout_flaky, max_attempts=3, base_delay=0.01)
        assert result == "recovered"
        assert call_count == 2

    def test_unexpected_exception_raises_immediately(self) -> None:
        def unexpected() -> None:
            raise ValueError("unexpected")

        with pytest.raises(ValueError, match="unexpected"):
            retry(unexpected, max_attempts=3)

    def test_exponential_backoff_delays(self) -> None:
        """Verify that delays increase exponentially (ignoring jitter)."""
        call_count = 0

        def always_fail() -> None:
            nonlocal call_count
            call_count += 1
            raise ConnectorError("fail")

        mock_sleep = MagicMock()
        with patch.object(time, "sleep", mock_sleep):
            with pytest.raises(ConnectorError):
                retry(always_fail, max_attempts=3, base_delay=1.0, jitter=0.0)

        assert mock_sleep.call_count == 2  # noqa: PLR2004 — 3 attempts = 2 sleeps
        # First delay: 1.0 * 2^0 = 1.0
        # Second delay: 1.0 * 2^1 = 2.0
        delays = [call.args[0] for call in mock_sleep.call_args_list]
        assert delays[0] == pytest.approx(1.0)
        assert delays[1] == pytest.approx(2.0)

    def test_max_delay_cap(self) -> None:
        call_count = 0

        def always_fail() -> None:
            nonlocal call_count
            call_count += 1
            raise ConnectorError("fail")

        mock_sleep = MagicMock()
        with patch.object(time, "sleep", mock_sleep):
            with pytest.raises(ConnectorError):
                retry(
                    always_fail,
                    max_attempts=3,
                    base_delay=20.0,
                    max_delay=5.0,
                    jitter=0.0,
                )

        delays = [call.args[0] for call in mock_sleep.call_args_list]
        for d in delays:
            assert d <= 5.0  # noqa: PLR2004

    def test_single_attempt_raises_without_sleep(self) -> None:
        def fail() -> None:
            raise ConnectorError("once")

        mock_sleep = MagicMock()
        with patch.object(time, "sleep", mock_sleep):
            with pytest.raises(ConnectorError, match="once"):
                retry(fail, max_attempts=1)

        mock_sleep.assert_not_called()
