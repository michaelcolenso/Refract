"""Tests for utils module."""

import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

from utils import retry_with_backoff


class TestRetryWithBackoff:
    """Tests for the retry_with_backoff decorator."""

    def test_successful_call_no_retry(self):
        """Function that succeeds should only be called once."""
        call_count = 0

        @retry_with_backoff(max_retries=3, initial_delay=0.01)
        def successful_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = successful_func()
        assert result == "success"
        assert call_count == 1

    def test_non_retryable_error_raises_immediately(self):
        """Non-retryable errors should raise immediately without retry."""
        call_count = 0

        @retry_with_backoff(max_retries=3, initial_delay=0.01)
        def failing_func():
            nonlocal call_count
            call_count += 1
            raise ValueError("Not a retryable error")

        with pytest.raises(ValueError, match="Not a retryable error"):
            failing_func()

        assert call_count == 1  # Should not retry

    def test_retryable_error_retries(self):
        """Retryable errors should trigger retry attempts."""
        call_count = 0

        @retry_with_backoff(max_retries=2, initial_delay=0.01)
        def rate_limited_func():
            nonlocal call_count
            call_count += 1
            raise Exception("rate limit exceeded")

        with pytest.raises(Exception, match="rate limit"):
            rate_limited_func()

        assert call_count == 3  # Initial + 2 retries

    def test_success_after_retry(self):
        """Function that succeeds after initial failures."""
        call_count = 0

        @retry_with_backoff(max_retries=3, initial_delay=0.01)
        def eventually_succeeds():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("429 too many requests")
            return "success"

        result = eventually_succeeds()
        assert result == "success"
        assert call_count == 3

    def test_retryable_error_patterns(self):
        """Various retryable error patterns should trigger retries."""
        retryable_errors = [
            "rate limit exceeded",
            "quota exceeded",
            "too many requests",
            "429 error",
            "timeout error",
            "temporarily unavailable",
            "service unavailable",
            "503 service unavailable",
            "500 internal server error",
        ]

        for error_msg in retryable_errors:
            call_count = 0

            @retry_with_backoff(max_retries=1, initial_delay=0.01)
            def failing_func():
                nonlocal call_count
                call_count += 1
                raise Exception(error_msg)

            with pytest.raises(Exception):
                failing_func()

            assert call_count == 2, f"Error '{error_msg}' should have triggered retry"

    def test_backoff_factor(self):
        """Delays should increase with backoff factor."""
        delays = []
        call_count = 0

        @retry_with_backoff(max_retries=2, initial_delay=0.1, backoff_factor=2.0)
        def rate_limited_func():
            nonlocal call_count
            call_count += 1
            raise Exception("rate limit")

        with patch('time.sleep') as mock_sleep:
            with pytest.raises(Exception):
                rate_limited_func()

            # Check that sleep was called with increasing delays
            sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]
            assert len(sleep_calls) == 2  # Two retries
            assert sleep_calls[0] == pytest.approx(0.1, rel=0.1)
            assert sleep_calls[1] == pytest.approx(0.2, rel=0.1)

    def test_preserves_function_metadata(self):
        """Decorator should preserve function name and docstring."""
        @retry_with_backoff()
        def my_function():
            """My docstring."""
            pass

        assert my_function.__name__ == "my_function"
        assert my_function.__doc__ == "My docstring."
