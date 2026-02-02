#!/usr/bin/env python3
"""
REFRACT Utilities - Shared helper functions and decorators.
"""

import hashlib
import time
from functools import wraps
from pathlib import Path
from typing import Optional


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


def image_hash(image_path: Path) -> str:
    """Compute SHA-256 hash of an image file for deduplication."""
    h = hashlib.sha256()
    with open(image_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def downscale_for_api(image_path: Path, max_long_edge: int = 2048) -> Optional[Path]:
    """
    Downscale an image if its longest edge exceeds max_long_edge.

    Returns a Path to a temporary downscaled file, or None if no
    downscaling was needed (original is already small enough).
    The caller is responsible for cleaning up the temporary file.
    """
    from PIL import Image

    with Image.open(image_path) as img:
        w, h = img.size
        long_edge = max(w, h)

        if long_edge <= max_long_edge:
            return None

        scale = max_long_edge / long_edge
        new_w = int(w * scale)
        new_h = int(h * scale)

        resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

        # Save to temp file next to original
        suffix = image_path.suffix if image_path.suffix else '.jpg'
        temp_path = image_path.parent / f"_api_resized_{image_path.stem}{suffix}"
        if suffix.lower() in ('.jpg', '.jpeg'):
            resized = resized.convert('RGB')
        resized.save(temp_path, quality=90)
        print(f"  Downscaled {w}x{h} -> {new_w}x{new_h} for API")
        return temp_path
