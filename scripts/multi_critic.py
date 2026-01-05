#!/usr/bin/env python3
"""
REFRACT Multi-Critic - Multi-LLM Photography Analysis Engine
Submits photographs to multiple LLMs for objective, diverse critiques.
"""

import os
import json
import sys
import base64
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from abc import ABC, abstractmethod
from PIL import Image
import io
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

                    print(f"      API error (attempt {attempt + 1}/{max_retries}): {e}")
                    print(f"      Retrying in {delay:.1f}s...")
                    time.sleep(delay)
                    delay *= backoff_factor

            raise last_exception
        return wrapper
    return decorator


class BaseCritic(ABC):
    """Abstract base class for LLM critics."""

    name: str = "base"

    @abstractmethod
    def analyze(self, image_path: Path) -> Dict[str, Any]:
        """Analyze a photograph and return structured critique."""
        pass

    def _get_prompt(self) -> str:
        """Standard prompt for all LLMs."""
        return """You are an expert photography critic. Analyze this photograph and provide feedback in STRICT JSON format only.

Your response must be ONLY valid JSON with no additional text, markdown formatting, or explanations.

Provide exactly this structure:
{
  "score": <number 0-100>,
  "improvements": ["specific actionable instruction 1", "specific actionable instruction 2", "specific actionable instruction 3"],
  "notes": "brief explanation of the score and why these improvements matter"
}

Guidelines for your analysis:
- score: Rate the overall quality (composition, lighting, exposure, colors, subject clarity)
- improvements: List 2-5 SPECIFIC, ACTIONABLE image editing instructions (e.g., "increase brightness by 20%", "boost vibrance in the blue tones", "crop to rule of thirds with subject in left third")
- notes: Brief reasoning (2-3 sentences max)

CRITICAL: Output ONLY the JSON object. No markdown, no code blocks, no additional text."""

    def _parse_response(self, response_text: str) -> Dict[str, Any]:
        """Parse and validate JSON response from any LLM."""
        response_text = response_text.strip()

        # Remove markdown code blocks if present
        if response_text.startswith('```'):
            lines = response_text.split('\n')
            response_text = '\n'.join(lines[1:-1])
        if response_text.startswith('json'):
            response_text = response_text[4:].strip()

        # Parse JSON
        critique = json.loads(response_text)

        # Validate structure
        required_keys = {'score', 'improvements', 'notes'}
        if not required_keys.issubset(critique.keys()):
            raise ValueError(f"Missing required keys. Expected {required_keys}, got {critique.keys()}")

        # Validate types
        if not isinstance(critique['score'], (int, float)):
            raise ValueError("Score must be a number")
        if not isinstance(critique['improvements'], list):
            raise ValueError("Improvements must be a list")
        if not isinstance(critique['notes'], str):
            raise ValueError("Notes must be a string")

        # Normalize score to 0-100
        critique['score'] = max(0, min(100, float(critique['score'])))

        return critique

    def _image_to_base64(self, image_path: Path) -> str:
        """Convert image to base64 string."""
        with open(image_path, "rb") as f:
            return base64.standard_b64encode(f.read()).decode("utf-8")

    def _get_image_media_type(self, image_path: Path) -> str:
        """Get the media type for an image."""
        suffix = image_path.suffix.lower()
        if suffix in ['.jpg', '.jpeg']:
            return "image/jpeg"
        elif suffix == '.png':
            return "image/png"
        elif suffix == '.gif':
            return "image/gif"
        elif suffix == '.webp':
            return "image/webp"
        return "image/jpeg"  # default


class GeminiCritic(BaseCritic):
    """Google Gemini Vision critic."""

    name = "gemini"

    def __init__(self, api_key: str):
        from google import genai
        self.client = genai.Client(api_key=api_key)
        self.model_name = 'gemini-2.5-flash-image'

    @retry_with_backoff(max_retries=3, initial_delay=2.0)
    def analyze(self, image_path: Path) -> Dict[str, Any]:
        img = Image.open(image_path)
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=[self._get_prompt(), img]
        )
        return self._parse_response(response.text)


class OpenAICritic(BaseCritic):
    """OpenAI GPT-4 Vision critic."""

    name = "openai"

    def __init__(self, api_key: str):
        from openai import OpenAI
        self.client = OpenAI(api_key=api_key)

    @retry_with_backoff(max_retries=3, initial_delay=2.0)
    def analyze(self, image_path: Path) -> Dict[str, Any]:
        base64_image = self._image_to_base64(image_path)
        media_type = self._get_image_media_type(image_path)

        response = self.client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": self._get_prompt()},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{media_type};base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=1000
        )
        return self._parse_response(response.choices[0].message.content)


class AnthropicCritic(BaseCritic):
    """Anthropic Claude Vision critic."""

    name = "anthropic"

    def __init__(self, api_key: str):
        import anthropic
        self.client = anthropic.Anthropic(api_key=api_key)

    @retry_with_backoff(max_retries=3, initial_delay=2.0)
    def analyze(self, image_path: Path) -> Dict[str, Any]:
        base64_image = self._image_to_base64(image_path)
        media_type = self._get_image_media_type(image_path)

        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": base64_image
                            }
                        },
                        {
                            "type": "text",
                            "text": self._get_prompt()
                        }
                    ]
                }
            ]
        )
        return self._parse_response(response.content[0].text)


class MultiCritic:
    """
    Orchestrates multiple LLM critics for diverse, objective photo analysis.

    Collects critiques from all configured LLMs and provides:
    - Individual critiques from each LLM
    - Consensus score (average)
    - Combined improvements (deduplicated)
    """

    def __init__(
        self,
        gemini_key: Optional[str] = None,
        openai_key: Optional[str] = None,
        anthropic_key: Optional[str] = None
    ):
        """
        Initialize MultiCritic with available API keys.
        At least one API key must be provided.
        """
        self.critics: List[BaseCritic] = []

        if gemini_key:
            try:
                self.critics.append(GeminiCritic(gemini_key))
                print(f"  Initialized Gemini critic")
            except Exception as e:
                print(f"  Warning: Failed to initialize Gemini critic: {e}")

        if openai_key:
            try:
                self.critics.append(OpenAICritic(openai_key))
                print(f"  Initialized OpenAI critic")
            except Exception as e:
                print(f"  Warning: Failed to initialize OpenAI critic: {e}")

        if anthropic_key:
            try:
                self.critics.append(AnthropicCritic(anthropic_key))
                print(f"  Initialized Anthropic critic")
            except Exception as e:
                print(f"  Warning: Failed to initialize Anthropic critic: {e}")

        if not self.critics:
            raise ValueError("At least one API key must be provided and valid")

    def analyze(self, image_path: Path) -> Dict[str, Any]:
        """
        Analyze a photograph using all configured LLM critics.

        Returns:
            Dictionary with:
            - critiques: List of individual critiques with LLM name
            - consensus_score: Average score across all LLMs
            - combined_improvements: All unique improvements
            - summary: Aggregated notes
            - score: Consensus score (for backward compatibility)
            - improvements: Combined improvements (for backward compatibility)
            - notes: Summary (for backward compatibility)
        """
        critiques = []
        scores = []
        all_improvements = []
        all_notes = []

        for critic in self.critics:
            try:
                print(f"    Getting critique from {critic.name}...")
                result = critic.analyze(image_path)
                result['llm'] = critic.name
                critiques.append(result)
                scores.append(result['score'])
                all_improvements.extend(result['improvements'])
                all_notes.append(f"[{critic.name.upper()}] {result['notes']}")
                print(f"      Score: {result['score']}/100")
            except Exception as e:
                print(f"    Warning: {critic.name} critique failed: {e}")
                critiques.append({
                    'llm': critic.name,
                    'error': str(e),
                    'score': None,
                    'improvements': [],
                    'notes': f"Analysis failed: {e}"
                })

        # Calculate consensus
        valid_scores = [s for s in scores if s is not None]
        consensus_score = sum(valid_scores) / len(valid_scores) if valid_scores else 0

        # Deduplicate improvements (simple approach - keep unique ones)
        seen = set()
        unique_improvements = []
        for imp in all_improvements:
            imp_lower = imp.lower().strip()
            if imp_lower not in seen:
                seen.add(imp_lower)
                unique_improvements.append(imp)

        # Create summary
        summary = " | ".join(all_notes) if all_notes else "No critiques available"

        return {
            'critiques': critiques,
            'consensus_score': round(consensus_score, 1),
            'combined_improvements': unique_improvements,
            'summary': summary,
            # Backward compatibility fields
            'score': round(consensus_score, 1),
            'improvements': unique_improvements[:5],  # Limit for editor
            'notes': summary
        }


def main():
    """CLI interface for the Multi-Critic."""
    if len(sys.argv) != 2:
        print("Usage: multi_critic.py <image_path>", file=sys.stderr)
        sys.exit(1)

    image_path = Path(sys.argv[1])

    if not image_path.exists():
        print(f"Error: Image not found: {image_path}", file=sys.stderr)
        sys.exit(1)

    # Get API keys from environment
    gemini_key = os.getenv('GEMINI_API_KEY')
    openai_key = os.getenv('OPENAI_API_KEY')
    anthropic_key = os.getenv('ANTHROPIC_API_KEY')

    if not any([gemini_key, openai_key, anthropic_key]):
        print("Error: At least one API key must be set:", file=sys.stderr)
        print("  GEMINI_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY", file=sys.stderr)
        sys.exit(1)

    print("Initializing critics...")
    multi_critic = MultiCritic(
        gemini_key=gemini_key,
        openai_key=openai_key,
        anthropic_key=anthropic_key
    )

    print(f"\nAnalyzing: {image_path.name}")
    result = multi_critic.analyze(image_path)

    # Output JSON
    print("\n" + "="*60)
    print("MULTI-LLM CRITIQUE RESULTS")
    print("="*60)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
