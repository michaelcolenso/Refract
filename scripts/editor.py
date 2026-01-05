#!/usr/bin/env python3
"""
REFRACT Editor - Photography Enhancement Engine
Uses Gemini Image Editing to apply improvements to photographs.
"""

import os
import sys
import json
import time
from pathlib import Path
from typing import List
from functools import wraps
from google import genai
from PIL import Image


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


class PhotoEditor:
    """Applies improvements to photographs using Gemini's image editing capabilities."""

    def __init__(self, api_key: str):
        """Initialize the Editor with Gemini API credentials."""
        self.client = genai.Client(api_key=api_key)
        # Using Gemini 3.0 for image editing
        self.model_name = 'gemini-3.0-flash'

    @retry_with_backoff(max_retries=3, initial_delay=2.0)
    def edit(self, image_path: Path, improvements: List[str], output_path: Path) -> bool:
        """
        Apply improvements to a photograph.

        Args:
            image_path: Path to the original image
            improvements: List of improvement instructions from the Critic
            output_path: Path to save the improved image

        Returns:
            True if successful, False otherwise
        """
        try:
            # Load the original image
            img = Image.open(image_path)

            # Combine improvements into a clear editing prompt
            improvements_text = "\n".join(f"- {imp}" for imp in improvements)

            prompt = f"""You are an expert photo editor. Edit this photograph to apply the following improvements while maintaining the original composition, subject, and overall character of the image.

Apply these specific improvements:
{improvements_text}

Important guidelines:
- Maintain the original subject and composition
- Apply adjustments naturally and subtly
- Preserve the artistic intent of the original photograph
- Focus on technical improvements (exposure, color, clarity, composition refinement)
- Do not add or remove major elements
- Ensure the result looks like an enhanced version of the original, not a different photo

Generate the improved version of this photograph."""

            # Generate the edited image
            # Note: Gemini's image editing capabilities work through the generative model
            # with the image as context and edit instructions
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[prompt, img]
            )

            # Check if response contains image data
            image_saved = False
            if hasattr(response, 'candidates') and len(response.candidates) > 0:
                candidate = response.candidates[0]
                if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                    for part in candidate.content.parts:
                        if hasattr(part, 'inline_data') and part.inline_data is not None:
                            # Save the generated image
                            image_data = part.inline_data.data
                            if image_data and len(image_data) > 100:  # Basic sanity check
                                output_path.write_bytes(image_data)
                                # Validate the saved image is actually valid
                                try:
                                    test_img = Image.open(output_path)
                                    test_img.verify()  # Verify it's a valid image
                                    print(f"Successfully edited image saved to: {output_path}")
                                    image_saved = True
                                    break
                                except Exception as verify_err:
                                    print(f"Generated image failed validation: {verify_err}", file=sys.stderr)
                                    output_path.unlink(missing_ok=True)  # Remove invalid file

            if not image_saved:
                # If no valid image was generated, fall back to using traditional PIL editing
                print("Note: Using fallback enhancement method", file=sys.stderr)
                edited_img = self._apply_basic_enhancements(img, improvements)
                # Ensure we save in a format PIL can read back
                if output_path.suffix.lower() in ['.jpg', '.jpeg']:
                    edited_img = edited_img.convert('RGB')  # Ensure RGB for JPEG
                edited_img.save(output_path, quality=95)
                # Validate the output
                test_img = Image.open(output_path)
                test_img.verify()

            return True

        except Exception as e:
            print(f"Error during image editing: {e}", file=sys.stderr)
            # Fallback: save enhanced version using basic PIL operations
            try:
                img = Image.open(image_path)
                edited_img = self._apply_basic_enhancements(img, improvements)
                if output_path.suffix.lower() in ['.jpg', '.jpeg']:
                    edited_img = edited_img.convert('RGB')
                edited_img.save(output_path, quality=95)
                # Validate
                test_img = Image.open(output_path)
                test_img.verify()
                print(f"Applied basic enhancements to: {output_path}")
                return True
            except Exception as e2:
                print(f"Fallback also failed: {e2}", file=sys.stderr)
                return False

    def _apply_basic_enhancements(self, img: Image.Image, improvements: List[str]) -> Image.Image:
        """
        Apply basic enhancements using PIL as a fallback.
        This is a simplified implementation that applies common improvements.
        """
        from PIL import ImageEnhance

        enhanced = img.copy()

        # Parse improvements and apply relevant PIL enhancements
        improvements_lower = [imp.lower() for imp in improvements]

        # Brightness adjustments
        if any('brightness' in imp or 'exposure' in imp or 'lighter' in imp or 'darker' in imp for imp in improvements_lower):
            enhancer = ImageEnhance.Brightness(enhanced)
            if any('increase' in imp or 'boost' in imp or 'lighter' in imp for imp in improvements_lower):
                enhanced = enhancer.enhance(1.15)
            elif any('decrease' in imp or 'reduce' in imp or 'darker' in imp for imp in improvements_lower):
                enhanced = enhancer.enhance(0.85)

        # Contrast adjustments
        if any('contrast' in imp for imp in improvements_lower):
            enhancer = ImageEnhance.Contrast(enhanced)
            if any('increase' in imp or 'boost' in imp for imp in improvements_lower):
                enhanced = enhancer.enhance(1.2)
            elif any('decrease' in imp or 'reduce' in imp or 'soften' in imp for imp in improvements_lower):
                enhanced = enhancer.enhance(0.8)

        # Color/saturation adjustments
        if any('saturation' in imp or 'vibrance' in imp or 'color' in imp for imp in improvements_lower):
            enhancer = ImageEnhance.Color(enhanced)
            if any('increase' in imp or 'boost' in imp or 'vibrant' in imp for imp in improvements_lower):
                enhanced = enhancer.enhance(1.2)
            elif any('decrease' in imp or 'reduce' in imp or 'muted' in imp for imp in improvements_lower):
                enhanced = enhancer.enhance(0.8)

        # Sharpness adjustments
        if any('sharp' in imp or 'clarity' in imp or 'detail' in imp for imp in improvements_lower):
            enhancer = ImageEnhance.Sharpness(enhanced)
            if any('increase' in imp or 'boost' in imp for imp in improvements_lower):
                enhanced = enhancer.enhance(1.3)

        return enhanced


def main():
    """CLI interface for the Editor."""
    if len(sys.argv) != 4:
        print("Usage: editor.py <image_path> <improvements_json> <output_path>", file=sys.stderr)
        sys.exit(1)

    image_path = Path(sys.argv[1])
    improvements_json = sys.argv[2]
    output_path = Path(sys.argv[3])

    if not image_path.exists():
        print(f"Error: Image not found: {image_path}", file=sys.stderr)
        sys.exit(1)

    # Parse improvements
    try:
        improvements = json.loads(improvements_json)
        if not isinstance(improvements, list):
            raise ValueError("Improvements must be a list")
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON for improvements: {e}", file=sys.stderr)
        sys.exit(1)

    # Get API key from environment
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable not set", file=sys.stderr)
        sys.exit(1)

    # Edit the image
    editor = PhotoEditor(api_key)
    success = editor.edit(image_path, improvements, output_path)

    if success:
        print(f"Image successfully edited: {output_path}")
        sys.exit(0)
    else:
        print("Error: Failed to edit image", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
