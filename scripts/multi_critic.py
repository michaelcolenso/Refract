#!/usr/bin/env python3
"""
REFRACT Multi-Critic - Multi-LLM Photography Analysis Engine
Submits photographs to multiple LLMs for objective, diverse critiques.
"""

import os
import json
import sys
import base64
from pathlib import Path
from typing import Dict, Any, List, Optional
from abc import ABC, abstractmethod
from PIL import Image
import io

from utils import retry_with_backoff


class BaseCritic(ABC):
    """Abstract base class for LLM critics."""

    name: str = "base"

    @abstractmethod
    def analyze(self, image_path: Path) -> Dict[str, Any]:
        """Analyze a photograph and return structured critique."""
        pass

    def _get_prompt(self) -> str:
        """Standard prompt for all LLMs."""
        return """You are a professional photography editor with expertise in post-processing. Analyze this photograph to identify improvements that can be made through editing software (like Lightroom or Photoshop).

IMPORTANT: Your response must be ONLY valid JSON with no additional text, markdown, or code blocks.

{
  "genre": "<portrait|landscape|street|wildlife|macro|architecture|product|event|abstract|other>",
  "subject": "<brief description of the main subject>",
  "mood": "<the emotional tone or atmosphere of the image>",
  "score": <number 0-100>,
  "technical_assessment": {
    "exposure": "<underexposed|slightly_under|good|slightly_over|overexposed>",
    "white_balance": "<too_cool|slightly_cool|neutral|slightly_warm|too_warm>",
    "focus": "<soft|acceptable|sharp|very_sharp>",
    "noise": "<none|low|moderate|high>"
  },
  "improvements": [
    {
      "action": "<specific editing action>",
      "intensity": "<subtle|moderate|significant>",
      "priority": <1-5 where 1 is highest priority>,
      "reason": "<why this improvement helps>"
    }
  ],
  "preserve": ["<aspect 1 to keep unchanged>", "<aspect 2 to keep unchanged>"],
  "notes": "<2-3 sentence summary of your analysis>"
}

ANALYSIS GUIDELINES:

1. RESPECT THE PHOTOGRAPHER'S INTENT
   - Identify intentional stylistic choices (high contrast B&W, vintage color grading, moody shadows)
   - Don't "fix" deliberate artistic decisions
   - Consider the genre conventions (street photography embraces grain, portraits need skin tone accuracy)

2. PRIORITIZE HIGH-IMPACT IMPROVEMENTS
   - Focus on edits that meaningfully improve the image
   - Limit to 3-5 improvements maximum
   - Rank by visual impact, not ease of implementation

3. BE SPECIFIC AND ACTIONABLE
   Good: "Lift shadows in the foreground by +20 to reveal detail while maintaining mood"
   Good: "Apply gentle S-curve to midtones for added depth"
   Good: "Reduce highlights on subject's forehead to recover skin detail"
   Bad: "Improve the lighting" (too vague)
   Bad: "Make it look better" (not actionable)

4. CONSIDER TECHNICAL CONSTRAINTS
   - Severely underexposed shadows may have noise if lifted too much
   - Blown highlights cannot be recovered
   - Heavy edits can introduce artifacts

5. SCORING GUIDE
   - 90-100: Exceptional, minimal editing needed
   - 75-89: Strong image, minor refinements beneficial
   - 60-74: Good foundation, moderate editing recommended
   - 45-59: Potential present, significant editing needed
   - Below 45: Major technical issues

Output ONLY the JSON object."""

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

        # Validate required fields
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

        # Handle new structured improvements format
        # Convert from [{action, intensity, priority, reason}] to string list for backward compatibility
        if critique['improvements'] and isinstance(critique['improvements'][0], dict):
            # Sort by priority (lower number = higher priority)
            sorted_improvements = sorted(
                critique['improvements'],
                key=lambda x: x.get('priority', 5)
            )
            # Store full structured data
            critique['improvements_detailed'] = sorted_improvements
            # Extract action strings with intensity for the editor
            critique['improvements'] = [
                f"[{imp.get('intensity', 'moderate').upper()}] {imp.get('action', '')}"
                for imp in sorted_improvements
            ]

        # Store additional context if present (for editor use)
        critique['context'] = {
            'genre': critique.get('genre', 'unknown'),
            'subject': critique.get('subject', ''),
            'mood': critique.get('mood', ''),
            'preserve': critique.get('preserve', []),
            'technical': critique.get('technical_assessment', {})
        }

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
        self.model_name = 'gemini-3-pro-preview'

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
            model="gpt-5.2",
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
            max_completion_tokens=1000
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
            model="claude-sonnet-4-5",
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
        all_improvements_detailed = []
        all_notes = []
        contexts = []

        for critic in self.critics:
            try:
                print(f"    Getting critique from {critic.name}...")
                result = critic.analyze(image_path)
                result['llm'] = critic.name
                critiques.append(result)
                scores.append(result['score'])
                all_improvements.extend(result['improvements'])
                if 'improvements_detailed' in result:
                    all_improvements_detailed.extend(result['improvements_detailed'])
                if 'context' in result:
                    contexts.append(result['context'])
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

        # Merge contexts from all critics (use most common values)
        merged_context = self._merge_contexts(contexts) if contexts else {}

        return {
            'critiques': critiques,
            'consensus_score': round(consensus_score, 1),
            'combined_improvements': unique_improvements,
            'improvements_detailed': all_improvements_detailed,
            'context': merged_context,
            'summary': summary,
            # Backward compatibility fields
            'score': round(consensus_score, 1),
            'improvements': unique_improvements[:5],  # Limit for editor
            'notes': summary
        }

    def _merge_contexts(self, contexts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Merge context information from multiple critics."""
        if not contexts:
            return {}

        # Use most common genre
        genres = [c.get('genre', 'unknown') for c in contexts if c.get('genre')]
        genre = max(set(genres), key=genres.count) if genres else 'unknown'

        # Combine subjects (use longest as it's likely most descriptive)
        subjects = [c.get('subject', '') for c in contexts if c.get('subject')]
        subject = max(subjects, key=len) if subjects else ''

        # Combine moods
        moods = [c.get('mood', '') for c in contexts if c.get('mood')]
        mood = max(moods, key=len) if moods else ''

        # Combine preserve lists (deduplicated)
        all_preserve = []
        for c in contexts:
            all_preserve.extend(c.get('preserve', []))
        preserve = list(dict.fromkeys(all_preserve))  # Dedupe while preserving order

        # Merge technical assessments (use most common values)
        technical = {}
        tech_fields = ['exposure', 'white_balance', 'focus', 'noise']
        for field in tech_fields:
            values = [c.get('technical', {}).get(field) for c in contexts if c.get('technical', {}).get(field)]
            if values:
                technical[field] = max(set(values), key=values.count)

        return {
            'genre': genre,
            'subject': subject,
            'mood': mood,
            'preserve': preserve,
            'technical': technical
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
