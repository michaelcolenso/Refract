#!/usr/bin/env python3
"""
REFRACT Editor - Photography Enhancement Engine
Uses Gemini Image Editing to apply improvements to photographs.
"""

import os
import sys
import json
import io
from pathlib import Path
from typing import List, Dict, Any, Optional, Iterable
import re
from google import genai
from PIL import Image

from utils import retry_with_backoff


class PhotoEditor:
    """Applies improvements to photographs using Gemini's image editing capabilities."""

    _IMPROVEMENT_TAG_RE = re.compile(
        r"^\s*\[(subtle|moderate|significant|strong|major|minor|severe|light|heavy)\]\s*",
        re.IGNORECASE
    )
    _FLASH_MODEL = "gemini-2.5-flash-image"
    _PRO_MODEL = "gemini-3-pro-image-preview"
    _ASPECT_RATIOS = {
        "1:1": 1.0,
        "2:3": 2 / 3,
        "3:2": 3 / 2,
        "3:4": 3 / 4,
        "4:3": 4 / 3,
        "4:5": 4 / 5,
        "5:4": 5 / 4,
        "9:16": 9 / 16,
        "16:9": 16 / 9,
        "21:9": 21 / 9,
    }

    def __init__(self, api_key: str):
        """Initialize the Editor with Gemini API credentials."""
        self.client = genai.Client(api_key=api_key)
        # Model selection: explicit model overrides policy; policy defaults to pro
        self.explicit_model = os.getenv("GEMINI_IMAGE_MODEL")
        self.model_policy = os.getenv("GEMINI_IMAGE_MODEL_POLICY", "pro").lower().strip()
        self.image_size = os.getenv("GEMINI_IMAGE_SIZE")
        self.aspect_ratio = os.getenv("GEMINI_IMAGE_ASPECT_RATIO")

        passes_env = os.getenv("GEMINI_IMAGE_PASSES", "1")
        try:
            self.max_passes = max(1, int(passes_env))
        except ValueError:
            self.max_passes = 1

    def _build_edit_prompt(
        self,
        improvements: List[str],
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Build a detailed editing prompt with context awareness."""

        # Format improvements list with explicit intensity
        parsed_improvements = []
        for imp in improvements:
            if not isinstance(imp, str):
                continue
            match = self._IMPROVEMENT_TAG_RE.match(imp)
            if match:
                intensity = match.group(1).lower()
                action = imp[match.end():].strip()
            else:
                intensity = "moderate"
                action = imp.strip()
            if action:
                parsed_improvements.append((action, intensity))

        if not parsed_improvements:
            parsed_improvements = [
                ("Apply a subtle, natural polish only if needed (exposure/contrast/white balance).", "subtle")
            ]

        improvements_text = "\n".join(
            f"{idx}. {action} (intensity: {intensity})"
            for idx, (action, intensity) in enumerate(parsed_improvements, 1)
        )

        # Build context section if available
        context_section = ""
        if context:
            genre = context.get('genre', 'unknown')
            subject = context.get('subject', '')
            mood = context.get('mood', '')
            preserve = context.get('preserve', [])
            technical = context.get('technical', {})

            context_parts = []
            if genre and genre != 'unknown':
                context_parts.append(f"Genre: {genre} photography")
            if subject:
                context_parts.append(f"Subject: {subject}")
            if mood:
                context_parts.append(f"Intended mood: {mood}")
            if technical:
                tech_items = [f"{k}: {v}" for k, v in technical.items() if v]
                if tech_items:
                    context_parts.append(f"Technical assessment: {', '.join(tech_items)}")

            if context_parts:
                context_section = "IMAGE CONTEXT:\n" + "\n".join(f"  • {p}" for p in context_parts) + "\n\n"

            # Build preserve section
            preserve_section = ""
            if preserve:
                preserve_section = "PRESERVE THESE ELEMENTS (do not alter):\n"
                preserve_section += "\n".join(f"  • {p}" for p in preserve) + "\n\n"
        else:
            preserve_section = ""

        # Genre-specific guidelines
        genre_guidelines = self._get_genre_guidelines(context.get('genre') if context else None)

        aspect_ratio_constraint = (
            "Cropping, straightening, and slight reframing are allowed if they improve composition and overall quality"
        )
        if self.aspect_ratio and self.aspect_ratio.strip().lower() not in {"", "auto"}:
            aspect_ratio_constraint = (
                "Cropping is allowed; adjust to the configured output aspect ratio if needed"
            )

        prompt = f"""You are a professional photo retoucher. Using the provided image, apply the requested edits to improve technical quality while preserving the original scene, subject identity, and artistic intent. Make precise, natural adjustments that improve the photo without changing its overall look.

{context_section}REQUESTED EDITS:
{improvements_text}

{preserve_section}EDITING PRINCIPLES:

0. SCORE OPTIMIZATION:
   • You may apply additional improvements beyond the list if they clearly improve the photo
   • Prioritize edits that would raise a professional critique score while keeping the result natural

1. HARD CONSTRAINTS:
   • Do NOT add, remove, or replace objects or people
   • {aspect_ratio_constraint}
   • Do NOT alter identity, age, or key features of subjects
   • Do NOT stylize or change the overall genre/look
   • Avoid artificial artifacts, halos, banding, or texture smearing

2. INTENSITY GUIDE (indicated in brackets):
   • [SUBTLE] = Minor refinement, barely noticeable (5-15% adjustment)
   • [MODERATE] = Clear improvement, still natural (15-30% adjustment)
   • [SIGNIFICANT] = Strong correction needed (30-50% adjustment)

3. TECHNICAL STANDARDS:
   • Maintain natural color relationships—avoid oversaturation or color casts
   • Preserve detail in highlights and shadows—no clipping
   • Keep noise levels appropriate to the image
   • Ensure smooth tonal gradations without banding
   • Maintain sharpness without halos or artifacts

4. QUALITY TARGETS:
   • The edit should look professional but not over-processed
   • Someone viewing before/after should think "that's better" not "that's different"
   • Edits should be invisible—the photo should look naturally good
{genre_guidelines}
Return only the edited image."""

        return prompt

    def _get_genre_guidelines(self, genre: Optional[str]) -> str:
        """Get genre-specific editing guidelines."""
        guidelines = {
            'portrait': """
4. PORTRAIT-SPECIFIC:
   • Maintain natural skin tones—avoid orange/magenta shifts
   • Keep skin texture visible (no plastic/airbrushed look)
   • Eyes should be clear but not unnaturally bright
   • Hair detail should be preserved
""",
            'landscape': """
4. LANDSCAPE-SPECIFIC:
   • Maintain realistic sky colors—avoid over-saturated blues
   • Keep foreground-background tonal balance
   • Preserve natural atmospheric perspective
   • Detail should be crisp but not over-sharpened
""",
            'street': """
4. STREET-SPECIFIC:
   • Embrace natural contrast and grain if present
   • Don't over-clean or sanitize the scene
   • Maintain the authentic urban atmosphere
   • Shadow detail is often intentionally dramatic
""",
            'wildlife': """
4. WILDLIFE-SPECIFIC:
   • Maintain natural fur/feather texture
   • Eye clarity is critical—should be sharp and alive
   • Background separation is important but keep it natural
   • Preserve environmental context
""",
            'macro': """
4. MACRO-SPECIFIC:
   • Maximize sharpness in the focal plane
   • Background bokeh should remain smooth
   • Color accuracy is critical for natural subjects
   • Fine detail and texture are paramount
""",
            'architecture': """
4. ARCHITECTURE-SPECIFIC:
   • Maintain straight verticals where appropriate
   • Balance interior/exterior exposure carefully
   • Preserve material textures (stone, glass, metal)
   • Keep lighting natural to the space
""",
            'product': """
4. PRODUCT-SPECIFIC:
   • Color accuracy is critical for commercial use
   • Clean highlights on reflective surfaces
   • Consistent lighting and shadow direction
   • Detail should be crisp and commercial-ready
""",
        }
        return guidelines.get(genre, """
4. GENERAL GUIDELINES:
   • Respect the photographic style and intent
   • Don't impose a different aesthetic
   • Enhance what's there rather than transform it
""")

    def _select_model(self, improvements: List[str]) -> str:
        """Select the best Gemini image model based on policy and edit complexity."""
        if self.explicit_model:
            return self.explicit_model

        policy = self.model_policy
        if policy in {"flash", "fast", "nano"}:
            return self._FLASH_MODEL
        if policy in {"pro", "quality", "auto"}:
            return self._PRO_MODEL
        return self._PRO_MODEL

    def _chunk_improvements(self, improvements: List[str]) -> List[List[str]]:
        """Split improvements into multiple passes when configured."""
        if self.max_passes <= 1 or len(improvements) <= 1:
            return [improvements]
        chunk_size = max(1, (len(improvements) + self.max_passes - 1) // self.max_passes)
        return [improvements[i:i + chunk_size] for i in range(0, len(improvements), chunk_size)]

    def _resolve_aspect_ratio(self, image_path: Path) -> Optional[str]:
        """Resolve aspect ratio from env or derive the closest supported ratio."""
        if not self.aspect_ratio:
            return None
        ratio_setting = self.aspect_ratio.strip()
        if ratio_setting.lower() == "auto":
            try:
                with Image.open(image_path) as img:
                    width, height = img.size
                if height == 0:
                    return None
                ratio = width / height
                return min(self._ASPECT_RATIOS.items(), key=lambda item: abs(item[1] - ratio))[0]
            except Exception:
                return None
        if ratio_setting in self._ASPECT_RATIOS:
            return ratio_setting
        print(f"Warning: Unsupported GEMINI_IMAGE_ASPECT_RATIO '{ratio_setting}' - ignoring", file=sys.stderr)
        return None

    def _build_generate_config(self, model_name: str, image_path: Path):
        """Build GenerateContentConfig for image-only output and optional sizing."""
        from google.genai import types

        config_kwargs = {"response_modalities": ["IMAGE"]}
        image_config_kwargs: Dict[str, str] = {}

        aspect_ratio = self._resolve_aspect_ratio(image_path)
        if aspect_ratio:
            image_config_kwargs["aspect_ratio"] = aspect_ratio

        if model_name == self._PRO_MODEL and self.image_size:
            image_size = self.image_size.strip().upper()
            if image_size in {"1K", "2K", "4K"}:
                image_config_kwargs["image_size"] = image_size
            else:
                print(f"Warning: Unsupported GEMINI_IMAGE_SIZE '{self.image_size}' - ignoring", file=sys.stderr)

        if image_config_kwargs:
            config_kwargs["image_config"] = types.ImageConfig(**image_config_kwargs)

        return types.GenerateContentConfig(**config_kwargs)

    def _iter_response_parts(self, response) -> Iterable[Any]:
        """Yield parts from a Gemini response, handling multiple response shapes."""
        if hasattr(response, "parts"):
            return response.parts
        if hasattr(response, "candidates") and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate, "content") and hasattr(candidate.content, "parts"):
                return candidate.content.parts
        return []

    def _extract_image_bytes(self, response) -> Optional[bytes]:
        """Extract the final (non-thought) image bytes from the response."""
        parts = list(self._iter_response_parts(response))
        if not parts:
            return None

        non_thought_images = []
        thought_images = []

        for part in parts:
            inline_data = getattr(part, "inline_data", None)
            if inline_data is None and hasattr(part, "inlineData"):
                inline_data = getattr(part, "inlineData", None)
            if not inline_data:
                continue
            data = getattr(inline_data, "data", None)
            if not data:
                continue
            if getattr(part, "thought", False):
                thought_images.append(data)
            else:
                non_thought_images.append(data)

        if non_thought_images:
            return non_thought_images[-1]
        if thought_images:
            return thought_images[-1]
        return None

    @retry_with_backoff(max_retries=3, initial_delay=2.0)
    def edit(
        self,
        image_path: Path,
        improvements: List[str],
        output_path: Path,
        context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Apply improvements to a photograph.

        Args:
            image_path: Path to the original image
            improvements: List of improvement instructions from the Critic
            output_path: Path to save the improved image
            context: Optional context about the image (genre, subject, mood, preserve list)

        Returns:
            True if successful, False otherwise
        """
        try:
            # Load the original image
            img = Image.open(image_path)

            image_data = None
            working_img = img

            for pass_index, pass_improvements in enumerate(self._chunk_improvements(improvements), 1):
                # Build the editing prompt with context
                prompt = self._build_edit_prompt(pass_improvements, context)

                # Select model and config per Google guidance
                model_name = self._select_model(pass_improvements)
                config = self._build_generate_config(model_name, image_path)

                # Generate the edited image
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=[prompt, working_img],
                    config=config
                )

                image_data = self._extract_image_bytes(response)
                if not image_data:
                    break

                try:
                    working_img = Image.open(io.BytesIO(image_data))
                    working_img.load()
                except Exception as decode_err:
                    print(f"Generated image decode failed on pass {pass_index}: {decode_err}", file=sys.stderr)
                    image_data = None
                    break

            # Check if response contains image data
            image_saved = False
            if image_data and len(image_data) > 100:  # Basic sanity check
                output_path.write_bytes(image_data)
                # Validate the saved image is actually valid
                try:
                    test_img = Image.open(output_path)
                    test_img.verify()  # Verify it's a valid image
                    print(f"Successfully edited image saved to: {output_path}")
                    image_saved = True
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
