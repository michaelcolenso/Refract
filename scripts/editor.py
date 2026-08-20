#!/usr/bin/env python3
"""Legacy generative editor compatibility layer.

Refract v2 uses DevelopEngine for ordinary photographic development. This file
remains for legacy/reimagine flows and now resolves its Gemini model through the
capability registry instead of pinning a retired preview model.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

from PIL import Image, ImageEnhance, ImageFilter

from refract.providers.registry import ModelRole, resolve_model_id
from utils import IMPROVEMENT_TAG_RE, retry_with_backoff


class PhotoEditor:
    _IMPROVEMENT_TAG_RE = IMPROVEMENT_TAG_RE

    def __init__(self, api_key: str):
        from google import genai

        self.client = genai.Client(api_key=api_key)
        self.model_name = resolve_model_id(
            role=ModelRole.EDIT,
            provider="google",
            env_var="GEMINI_IMAGE_MODEL",
            strict=False,
        )

    def _build_edit_prompt(
        self, improvements: list[str], context: Optional[dict[str, Any]] = None
    ) -> str:
        parsed = []
        for imp in improvements:
            if not isinstance(imp, str):
                continue
            match = self._IMPROVEMENT_TAG_RE.match(imp)
            intensity = match.group(1).lower() if match else "moderate"
            action = imp[match.end():].strip() if match else imp.strip()
            if action:
                parsed.append((action, intensity))
        requested = "\n".join(
            f"{i}. {action} (intensity: {intensity})"
            for i, (action, intensity) in enumerate(parsed, 1)
        )
        context = context or {}
        preserve = "\n".join(f"- {item}" for item in context.get("preserve", []))
        return f"""Edit the supplied photograph conservatively. Preserve scene identity, subject identity, composition, framing, aspect ratio, and artistic intent.

REQUESTED EDITS
{requested}

PRESERVE
{preserve or '- all unrequested content and structure'}

Hard constraints:
- do not add/remove/replace objects or people
- do not change crop or aspect ratio
- do not alter identity, age, facial features, text, or architecture
- do not stylize the image
- avoid halos, banding, smearing, invented texture, and oversaturation

Return only the edited image."""

    @retry_with_backoff(max_retries=3, initial_delay=2.0)
    def edit(
        self,
        image_path: Path,
        improvements: list[str],
        output_path: Path,
        context: Optional[dict[str, Any]] = None,
    ) -> bool:
        try:
            with Image.open(image_path) as opened:
                img = opened.convert("RGB")
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[self._build_edit_prompt(improvements, context), img],
            )
            for candidate in getattr(response, "candidates", []) or []:
                content = getattr(candidate, "content", None)
                for part in getattr(content, "parts", []) or []:
                    inline = getattr(part, "inline_data", None)
                    data = getattr(inline, "data", None)
                    if data and len(data) > 100:
                        output_path.write_bytes(data)
                        with Image.open(output_path) as check:
                            check.verify()
                        return True
        except Exception as exc:
            print(f"Generative legacy editor failed: {exc}", file=sys.stderr)

        try:
            with Image.open(image_path) as opened:
                fallback = self._apply_basic_enhancements(opened.convert("RGB"), improvements)
            fallback.save(output_path, quality=95)
            return True
        except Exception as exc:
            print(f"Legacy fallback failed: {exc}", file=sys.stderr)
            return False

    def _parse_intensity(self, improvement: str) -> float:
        match = self._IMPROVEMENT_TAG_RE.match(improvement.lower())
        if not match:
            return 1.0
        return {
            "subtle": 0.5,
            "light": 0.5,
            "minor": 0.5,
            "significant": 1.5,
            "strong": 1.5,
            "major": 1.5,
            "heavy": 1.5,
            "severe": 1.5,
        }.get(match.group(1), 1.0)

    def _apply_basic_enhancements(self, img: Image.Image, improvements: list[str]) -> Image.Image:
        out = img.copy()
        for imp in improvements:
            text = imp.lower()
            strength = self._parse_intensity(imp)
            if any(k in text for k in ("brightness", "exposure", "lighter")):
                out = ImageEnhance.Brightness(out).enhance(1 + 0.12 * strength)
            elif any(k in text for k in ("contrast", "s-curve", "tonal")):
                out = ImageEnhance.Contrast(out).enhance(1 + 0.15 * strength)
            elif any(k in text for k in ("saturation", "vibrance", "color")):
                out = ImageEnhance.Color(out).enhance(1 + 0.12 * strength)
            elif any(k in text for k in ("sharp", "detail", "crisp")):
                out = ImageEnhance.Sharpness(out).enhance(1 + 0.20 * strength)
            elif any(k in text for k in ("noise", "denoise")):
                out = out.filter(ImageFilter.GaussianBlur(radius=0.5 * strength))
        return out


def main() -> None:
    if len(sys.argv) != 4:
        print("Usage: editor.py <image_path> <improvements_json> <output_path>", file=sys.stderr)
        raise SystemExit(1)
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        print("Error: GEMINI_API_KEY environment variable not set", file=sys.stderr)
        raise SystemExit(1)
    improvements = json.loads(sys.argv[2])
    if not isinstance(improvements, list):
        raise SystemExit("improvements must be a JSON list")
    ok = PhotoEditor(key).edit(Path(sys.argv[1]), improvements, Path(sys.argv[3]))
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
