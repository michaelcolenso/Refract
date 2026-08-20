#!/usr/bin/env python3
"""Legacy-compatible multi-provider photo critic.

This module remains the v1 compatibility surface while Refract v2 moves toward
one structured reviewer + independent judge. Model IDs now come from the v2
capability registry so retired defaults cannot be buried here.
"""

from __future__ import annotations

import base64
import json
import os
import sys
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Optional

from PIL import Image

from refract.providers.registry import ModelRole, resolve_model_id
from utils import detect_media_type, retry_with_backoff


class BaseCritic(ABC):
    name = "base"

    @abstractmethod
    def analyze(self, image_path: Path) -> dict[str, Any]:
        raise NotImplementedError

    def _get_prompt(self) -> str:
        return """You are a professional photography editor. Analyze the photograph for editability, technical quality, composition, color, tonality, subject impact, and artistic intent.

IMPORTANT: Return ONLY valid JSON. No markdown or prose outside the JSON object.

{
  "genre": "<genre>",
  "subject": "<main subject>",
  "mood": "<intended mood>",
  "score": <0-100>,
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
      "priority": <1-5>,
      "reason": "<why it helps>"
    }
  ],
  "preserve": ["<intentional quality to preserve>"],
  "notes": "<brief summary>"
}

Respect intentional style. Do not suggest generic normalization. Prefer 3-5 high-impact, actionable edits. Output ONLY valid JSON."""

    def _parse_response(self, response_text: str) -> dict[str, Any]:
        response_text = response_text.strip()
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            response_text = "\n".join(lines[1:-1])
        if response_text.startswith("json"):
            response_text = response_text[4:].strip()

        critique = json.loads(response_text)
        required_keys = {"score", "improvements", "notes"}
        if not required_keys.issubset(critique.keys()):
            raise ValueError(
                f"Missing required keys. Expected {required_keys}, got {critique.keys()}"
            )
        if not isinstance(critique["score"], (int, float)):
            raise ValueError("Score must be a number")
        if not isinstance(critique["improvements"], list):
            raise ValueError("Improvements must be a list")
        if not isinstance(critique["notes"], str):
            raise ValueError("Notes must be a string")

        critique["score"] = max(0, min(100, float(critique["score"])))
        if critique["improvements"] and isinstance(critique["improvements"][0], dict):
            detailed = sorted(
                critique["improvements"], key=lambda x: x.get("priority", 5)
            )
            critique["improvements_detailed"] = detailed
            critique["improvements"] = [
                f"[{imp.get('intensity', 'moderate').upper()}] {imp.get('action', '')}"
                for imp in detailed
            ]

        critique["context"] = {
            "genre": critique.get("genre", "unknown"),
            "subject": critique.get("subject", ""),
            "mood": critique.get("mood", ""),
            "preserve": critique.get("preserve", []),
            "technical": critique.get("technical_assessment", {}),
        }
        return critique

    def _image_to_base64(self, image_path: Path) -> str:
        return base64.standard_b64encode(image_path.read_bytes()).decode("utf-8")

    def _get_image_media_type(self, image_path: Path) -> str:
        return detect_media_type(image_path)


class GeminiCritic(BaseCritic):
    name = "gemini"

    def __init__(self, api_key: str):
        from google import genai

        self.client = genai.Client(api_key=api_key)
        self.model_name = resolve_model_id(
            role=ModelRole.REVIEW,
            provider="google",
            env_var="GEMINI_CRITIC_MODEL",
            strict=False,
        )

    @retry_with_backoff(max_retries=3, initial_delay=2.0)
    def analyze(self, image_path: Path) -> dict[str, Any]:
        with Image.open(image_path) as img:
            response = self.client.models.generate_content(
                model=self.model_name, contents=[self._get_prompt(), img]
            )
        return self._parse_response(response.text)


class OpenAICritic(BaseCritic):
    name = "openai"

    def __init__(self, api_key: str):
        from openai import OpenAI

        self.client = OpenAI(api_key=api_key)
        self.model_name = resolve_model_id(
            role=ModelRole.REVIEW,
            provider="openai",
            env_var="OPENAI_CRITIC_MODEL",
            strict=False,
        )

    @retry_with_backoff(max_retries=3, initial_delay=2.0)
    def analyze(self, image_path: Path) -> dict[str, Any]:
        payload = self._image_to_base64(image_path)
        media_type = self._get_image_media_type(image_path)
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": self._get_prompt()},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{media_type};base64,{payload}"},
                        },
                    ],
                }
            ],
            max_completion_tokens=1200,
        )
        return self._parse_response(response.choices[0].message.content)


class AnthropicCritic(BaseCritic):
    name = "anthropic"

    def __init__(self, api_key: str):
        import anthropic

        self.client = anthropic.Anthropic(api_key=api_key)
        self.model_name = resolve_model_id(
            role=ModelRole.REVIEW,
            provider="anthropic",
            env_var="ANTHROPIC_CRITIC_MODEL",
            strict=False,
        )

    @retry_with_backoff(max_retries=3, initial_delay=2.0)
    def analyze(self, image_path: Path) -> dict[str, Any]:
        response = self.client.messages.create(
            model=self.model_name,
            max_tokens=1200,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": self._get_image_media_type(image_path),
                                "data": self._image_to_base64(image_path),
                            },
                        },
                        {"type": "text", "text": self._get_prompt()},
                    ],
                }
            ],
        )
        return self._parse_response(response.content[0].text)


class MultiCritic:
    """Legacy parallel critic aggregator.

    `consensus_valid` is false when fewer than two critics succeed. The numeric
    `consensus_score` remains for legacy templates, but callers must not present
    it as a model consensus unless consensus_valid is true.
    """

    def __init__(
        self,
        gemini_key: Optional[str] = None,
        openai_key: Optional[str] = None,
        anthropic_key: Optional[str] = None,
    ):
        self.critics: list[BaseCritic] = []
        for key, cls in [
            (gemini_key, GeminiCritic),
            (openai_key, OpenAICritic),
            (anthropic_key, AnthropicCritic),
        ]:
            if key:
                try:
                    self.critics.append(cls(key))
                except Exception as exc:
                    print(f"  Warning: Failed to initialize {cls.name} critic: {exc}")
        if not self.critics:
            raise ValueError("At least one API key must be provided and valid")

    def _run_critic(self, critic: BaseCritic, image_path: Path) -> dict[str, Any]:
        result = critic.analyze(image_path)
        result["llm"] = critic.name
        return result

    def analyze(self, image_path: Path) -> dict[str, Any]:
        critiques: list[dict[str, Any]] = []
        valid: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=max(1, len(self.critics))) as executor:
            futures = {
                executor.submit(self._run_critic, critic, image_path): critic
                for critic in self.critics
            }
            for future in as_completed(futures):
                critic = futures[future]
                try:
                    result = future.result()
                    critiques.append(result)
                    valid.append(result)
                except Exception as exc:
                    critiques.append(
                        {
                            "llm": critic.name,
                            "error": str(exc),
                            "score": None,
                            "improvements": [],
                            "notes": f"Analysis failed: {exc}",
                        }
                    )

        scores = [float(item["score"]) for item in valid]
        score = round(sum(scores) / len(scores), 1) if scores else 0.0
        consensus_valid = len(scores) >= 2
        critics_disagree = consensus_valid and max(scores) - min(scores) >= 20

        improvements: list[str] = []
        detailed: list[dict[str, Any]] = []
        seen: set[str] = set()
        contexts: list[dict[str, Any]] = []
        notes: list[str] = []
        for item in valid:
            for improvement in item.get("improvements", []):
                key = improvement.lower().strip()
                if key not in seen:
                    seen.add(key)
                    improvements.append(improvement)
            detailed.extend(item.get("improvements_detailed", []))
            if item.get("context"):
                contexts.append(item["context"])
            notes.append(f"[{item['llm'].upper()}] {item.get('notes', '')}")

        context = self._merge_contexts(contexts) if contexts else {}
        summary = " | ".join(notes) if notes else "No critiques available"
        return {
            "critiques": critiques,
            "valid_critic_count": len(scores),
            "consensus_valid": consensus_valid,
            "consensus_status": "consensus" if consensus_valid else ("single_critic" if scores else "unavailable"),
            "consensus_score": score,
            "combined_improvements": improvements,
            "improvements_detailed": detailed,
            "context": context,
            "summary": summary,
            "critics_disagree": critics_disagree,
            "score": score,
            "improvements": improvements[:5],
            "notes": summary,
        }

    def _merge_contexts(self, contexts: list[dict[str, Any]]) -> dict[str, Any]:
        if not contexts:
            return {}
        genres = [c.get("genre", "unknown") for c in contexts if c.get("genre")]
        subjects = [c.get("subject", "") for c in contexts if c.get("subject")]
        moods = [c.get("mood", "") for c in contexts if c.get("mood")]
        preserve: list[str] = []
        for c in contexts:
            preserve.extend(c.get("preserve", []))
        technical = {}
        for field in ["exposure", "white_balance", "focus", "noise"]:
            values = [
                c.get("technical", {}).get(field)
                for c in contexts
                if c.get("technical", {}).get(field)
            ]
            if values:
                technical[field] = max(set(values), key=values.count)
        return {
            "genre": max(set(genres), key=genres.count) if genres else "unknown",
            "subject": max(subjects, key=len) if subjects else "",
            "mood": max(moods, key=len) if moods else "",
            "preserve": list(dict.fromkeys(preserve)),
            "technical": technical,
        }


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: multi_critic.py <image_path>", file=sys.stderr)
        raise SystemExit(1)
    path = Path(sys.argv[1])
    critic = MultiCritic(
        gemini_key=os.getenv("GEMINI_API_KEY"),
        openai_key=os.getenv("OPENAI_API_KEY"),
        anthropic_key=os.getenv("ANTHROPIC_API_KEY"),
    )
    print(json.dumps(critic.analyze(path), indent=2))


if __name__ == "__main__":
    main()
