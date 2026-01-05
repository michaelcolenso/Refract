#!/usr/bin/env python3
"""
REFRACT Critic - Photography Analysis Engine
Uses Gemini Vision to analyze photographs and suggest improvements.
"""

import os
import json
import sys
from pathlib import Path
from typing import Dict, Any
from google import genai
from PIL import Image


class PhotoCritic:
    """Analyzes photographs using Gemini Vision and provides structured feedback."""

    def __init__(self, api_key: str):
        """Initialize the Critic with Gemini API credentials."""
        self.client = genai.Client(api_key=api_key)
        self.model_name = 'gemini-2.5-flash-image'

    def analyze(self, image_path: Path) -> Dict[str, Any]:
        """
        Analyze a photograph and return structured critique.

        Args:
            image_path: Path to the image file

        Returns:
            Dictionary with score, improvements, and notes
        """
        # Load and prepare image
        img = Image.open(image_path)

        # Craft the prompt for strict JSON output
        prompt = """You are an expert photography critic. Analyze this photograph and provide feedback in STRICT JSON format only.

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

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[prompt, img]
            )

            # Extract JSON from response
            response_text = response.text.strip()

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

        except json.JSONDecodeError as e:
            print(f"Error: Failed to parse JSON from Gemini response", file=sys.stderr)
            print(f"Response was: {response_text}", file=sys.stderr)
            raise
        except Exception as e:
            print(f"Error during analysis: {e}", file=sys.stderr)
            raise


def main():
    """CLI interface for the Critic."""
    if len(sys.argv) != 2:
        print("Usage: critic.py <image_path>", file=sys.stderr)
        sys.exit(1)

    image_path = Path(sys.argv[1])

    if not image_path.exists():
        print(f"Error: Image not found: {image_path}", file=sys.stderr)
        sys.exit(1)

    # Get API key from environment
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable not set", file=sys.stderr)
        sys.exit(1)

    # Analyze the image
    critic = PhotoCritic(api_key)
    result = critic.analyze(image_path)

    # Output JSON
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
