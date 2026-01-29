"""Tests for multi_critic module."""

import sys
import json
from pathlib import Path

import pytest

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

from multi_critic import BaseCritic


class MockCritic(BaseCritic):
    """Mock critic for testing base class methods."""

    name = "mock"

    def analyze(self, image_path):
        return {}


class TestBaseCriticParseResponse:
    """Tests for the _parse_response method."""

    def setup_method(self):
        """Create a mock critic for each test."""
        self.critic = MockCritic()

    def test_valid_json_response(self):
        """Valid JSON response should parse correctly."""
        response = json.dumps({
            "score": 85,
            "improvements": ["Increase brightness", "Boost contrast"],
            "notes": "Good composition overall."
        })

        result = self.critic._parse_response(response)

        assert result["score"] == 85
        assert len(result["improvements"]) == 2
        assert result["notes"] == "Good composition overall."

    def test_json_with_markdown_code_block(self):
        """JSON wrapped in markdown code blocks should be handled."""
        response = """```json
{
  "score": 75,
  "improvements": ["Test improvement"],
  "notes": "Test notes"
}
```"""

        result = self.critic._parse_response(response)

        assert result["score"] == 75
        assert result["improvements"] == ["Test improvement"]

    def test_json_with_just_json_prefix(self):
        """JSON with 'json' prefix should be handled."""
        response = """json
{
  "score": 90,
  "improvements": ["Test"],
  "notes": "Notes"
}"""

        result = self.critic._parse_response(response)

        assert result["score"] == 90

    def test_score_normalization_above_100(self):
        """Scores above 100 should be clamped to 100."""
        response = json.dumps({
            "score": 150,
            "improvements": [],
            "notes": ""
        })

        result = self.critic._parse_response(response)

        assert result["score"] == 100

    def test_score_normalization_below_0(self):
        """Scores below 0 should be clamped to 0."""
        response = json.dumps({
            "score": -10,
            "improvements": [],
            "notes": ""
        })

        result = self.critic._parse_response(response)

        assert result["score"] == 0

    def test_score_as_float(self):
        """Float scores should be accepted and normalized."""
        response = json.dumps({
            "score": 85.5,
            "improvements": [],
            "notes": ""
        })

        result = self.critic._parse_response(response)

        assert result["score"] == 85.5

    def test_missing_score_raises_error(self):
        """Missing score field should raise ValueError."""
        response = json.dumps({
            "improvements": [],
            "notes": ""
        })

        with pytest.raises(ValueError, match="Missing required keys"):
            self.critic._parse_response(response)

    def test_missing_improvements_raises_error(self):
        """Missing improvements field should raise ValueError."""
        response = json.dumps({
            "score": 80,
            "notes": ""
        })

        with pytest.raises(ValueError, match="Missing required keys"):
            self.critic._parse_response(response)

    def test_missing_notes_raises_error(self):
        """Missing notes field should raise ValueError."""
        response = json.dumps({
            "score": 80,
            "improvements": []
        })

        with pytest.raises(ValueError, match="Missing required keys"):
            self.critic._parse_response(response)

    def test_invalid_score_type_raises_error(self):
        """Non-numeric score should raise ValueError."""
        response = json.dumps({
            "score": "high",
            "improvements": [],
            "notes": ""
        })

        with pytest.raises(ValueError, match="Score must be a number"):
            self.critic._parse_response(response)

    def test_invalid_improvements_type_raises_error(self):
        """Non-list improvements should raise ValueError."""
        response = json.dumps({
            "score": 80,
            "improvements": "Single improvement",
            "notes": ""
        })

        with pytest.raises(ValueError, match="Improvements must be a list"):
            self.critic._parse_response(response)

    def test_invalid_notes_type_raises_error(self):
        """Non-string notes should raise ValueError."""
        response = json.dumps({
            "score": 80,
            "improvements": [],
            "notes": 123
        })

        with pytest.raises(ValueError, match="Notes must be a string"):
            self.critic._parse_response(response)

    def test_invalid_json_raises_error(self):
        """Invalid JSON should raise JSONDecodeError."""
        response = "not valid json {{"

        with pytest.raises(json.JSONDecodeError):
            self.critic._parse_response(response)

    def test_whitespace_handling(self):
        """Whitespace around JSON should be trimmed."""
        response = """

  {"score": 70, "improvements": [], "notes": ""}

"""

        result = self.critic._parse_response(response)

        assert result["score"] == 70

    def test_structured_improvements_format(self):
        """Structured improvements should be parsed and converted to string list."""
        response = json.dumps({
            "score": 78,
            "genre": "landscape",
            "subject": "Mountain lake at sunset",
            "mood": "serene",
            "improvements": [
                {
                    "action": "Lift shadows in foreground",
                    "intensity": "moderate",
                    "priority": 1,
                    "reason": "Reveal detail in rocks"
                },
                {
                    "action": "Boost vibrance in sky",
                    "intensity": "subtle",
                    "priority": 2,
                    "reason": "Enhance sunset colors"
                }
            ],
            "preserve": ["reflection clarity", "natural color balance"],
            "notes": "Strong composition with good light."
        })

        result = self.critic._parse_response(response)

        # Should have converted to string format with intensity prefix
        assert len(result["improvements"]) == 2
        assert "[MODERATE]" in result["improvements"][0]
        assert "Lift shadows" in result["improvements"][0]
        assert "[SUBTLE]" in result["improvements"][1]

        # Should preserve detailed version
        assert "improvements_detailed" in result
        assert len(result["improvements_detailed"]) == 2
        assert result["improvements_detailed"][0]["priority"] == 1

        # Should have context
        assert "context" in result
        assert result["context"]["genre"] == "landscape"
        assert result["context"]["subject"] == "Mountain lake at sunset"
        assert "reflection clarity" in result["context"]["preserve"]

    def test_structured_improvements_sorted_by_priority(self):
        """Structured improvements should be sorted by priority (lowest first)."""
        response = json.dumps({
            "score": 80,
            "improvements": [
                {"action": "Low priority", "intensity": "subtle", "priority": 3, "reason": ""},
                {"action": "High priority", "intensity": "significant", "priority": 1, "reason": ""},
                {"action": "Medium priority", "intensity": "moderate", "priority": 2, "reason": ""}
            ],
            "notes": "Test"
        })

        result = self.critic._parse_response(response)

        assert "High priority" in result["improvements"][0]
        assert "Medium priority" in result["improvements"][1]
        assert "Low priority" in result["improvements"][2]

    def test_context_populated_from_response(self):
        """Context should be populated from response fields."""
        response = json.dumps({
            "score": 85,
            "genre": "portrait",
            "subject": "Woman in garden",
            "mood": "peaceful",
            "technical_assessment": {
                "exposure": "good",
                "white_balance": "slightly_warm",
                "focus": "sharp",
                "noise": "low"
            },
            "improvements": ["Test improvement"],
            "preserve": ["skin tones", "background bokeh"],
            "notes": "Nice portrait."
        })

        result = self.critic._parse_response(response)

        assert result["context"]["genre"] == "portrait"
        assert result["context"]["subject"] == "Woman in garden"
        assert result["context"]["mood"] == "peaceful"
        assert result["context"]["technical"]["exposure"] == "good"
        assert result["context"]["technical"]["focus"] == "sharp"
        assert "skin tones" in result["context"]["preserve"]

    def test_legacy_string_improvements_still_work(self):
        """Legacy string array improvements should still work."""
        response = json.dumps({
            "score": 75,
            "improvements": ["Increase brightness", "Boost contrast"],
            "notes": "Good shot."
        })

        result = self.critic._parse_response(response)

        # Should remain as strings (no conversion)
        assert result["improvements"] == ["Increase brightness", "Boost contrast"]
        # Should still have context (empty/default)
        assert "context" in result


class TestBaseCriticGetPrompt:
    """Tests for the _get_prompt method."""

    def test_prompt_contains_required_elements(self):
        """Prompt should contain key instructions."""
        critic = MockCritic()
        prompt = critic._get_prompt()

        assert "score" in prompt.lower()
        assert "improvements" in prompt.lower()
        assert "notes" in prompt.lower()
        assert "json" in prompt.lower()

    def test_prompt_requests_json_only(self):
        """Prompt should request JSON-only output."""
        critic = MockCritic()
        prompt = critic._get_prompt()

        assert "ONLY valid JSON" in prompt or "only the JSON" in prompt.lower()


class TestBaseCriticImageHelpers:
    """Tests for image helper methods."""

    def test_get_image_media_type_jpeg(self):
        """JPEG files should return correct media type."""
        critic = MockCritic()

        assert critic._get_image_media_type(Path("test.jpg")) == "image/jpeg"
        assert critic._get_image_media_type(Path("test.jpeg")) == "image/jpeg"
        assert critic._get_image_media_type(Path("TEST.JPG")) == "image/jpeg"

    def test_get_image_media_type_png(self):
        """PNG files should return correct media type."""
        critic = MockCritic()

        assert critic._get_image_media_type(Path("test.png")) == "image/png"
        assert critic._get_image_media_type(Path("TEST.PNG")) == "image/png"

    def test_get_image_media_type_webp(self):
        """WebP files should return correct media type."""
        critic = MockCritic()

        assert critic._get_image_media_type(Path("test.webp")) == "image/webp"

    def test_get_image_media_type_unknown_defaults_to_jpeg(self):
        """Unknown file types should default to JPEG."""
        critic = MockCritic()

        assert critic._get_image_media_type(Path("test.unknown")) == "image/jpeg"
