#!/usr/bin/env python3
"""
REFRACT Utilities - Shared helper functions and decorators.
"""

import time
from functools import wraps


def retry_with_backoff(max_retries=3, initial_delay=2.0, backoff_factor=2.0):
    """
    Decorator to retry API calls with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds before first retry
        backoff_factor: Multiplier for delay between retries
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    error_msg = str(e).lower()

                    # Check if it's a rate limit or temporary error
                    is_retryable = any([
                        'rate limit' in error_msg,
                        'quota' in error_msg,
                        'too many requests' in error_msg,
                        '429' in error_msg,
                        'timeout' in error_msg,
                        'temporarily unavailable' in error_msg,
                        'service unavailable' in error_msg,
                        '503' in error_msg,
                        '500' in error_msg
                    ])

                    if not is_retryable or attempt == max_retries:
                        raise

                    print(f"  API error (attempt {attempt + 1}/{max_retries}): {e}")
                    print(f"  Retrying in {delay:.1f}s...")
                    time.sleep(delay)
                    delay *= backoff_factor

            raise last_exception
        return wrapper
    return decorator
