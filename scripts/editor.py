#!/usr/bin/env python3
"""
REFRACT Editor - Photography Enhancement Engine
Uses Gemini Image Editing to apply improvements to photographs.
"""

import os
import sys
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from google import genai
from PIL import Image

from utils import retry_with_backoff, IMPROVEMENT_TAG_RE


class PhotoEditor:
    """Applies improvements to photographs using Gemini's image editing capabilities."""

    _IMPROVEMENT_TAG_RE = IMPROVEMENT_TAG_RE

    def __init__(self, api_key: str):
        """Initialize the Editor with Gemini API credentials."""
        self.client = genai.Client(api_key=api_key)
        # Using Gemini 3 Pro Preview for image editing
        self.model_name = 'gemini-3-pro-image-preview'

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

        prompt = f"""You are a professional photo retoucher. Edit the provided photo to improve technical quality while preserving the original scene, subject identity, and artistic intent. Make realistic, natural edits only.

{context_section}REQUESTED EDITS:
{improvements_text}

{preserve_section}EDITING PRINCIPLES:

1. HARD CONSTRAINTS:
   • Do NOT add, remove, or replace objects or people
   • Do NOT change framing, crop, or aspect ratio
   • Do NOT alter identity, age, or key features of subjects
   • Do NOT stylize or change the overall genre/look
   • Avoid artificial artifacts, halos, banding, or texture smearing

2. INTENSITY GUIDE:
   • subtle = minor refinement (5-15% adjustment)
   • moderate = clear improvement, still natural (15-30% adjustment)
   • significant = strong correction when needed (30-45% adjustment)

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

            # Build the editing prompt with context
            prompt = self._build_edit_prompt(improvements, context)

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

    def _parse_intensity(self, improvement: str) -> float:
        """Extract intensity multiplier from an improvement string."""
        imp_lower = improvement.lower()
        match = self._IMPROVEMENT_TAG_RE.match(imp_lower)
        if match:
            tag = match.group(1)
            if tag in ('subtle', 'light', 'minor'):
                return 0.5
            elif tag in ('significant', 'strong', 'major', 'heavy', 'severe'):
                return 1.5
        return 1.0  # moderate/default

    def _apply_basic_enhancements(self, img: Image.Image, improvements: List[str]) -> Image.Image:
        """
        Apply enhancements using PIL as a fallback.
        Maps LLM improvement suggestions to concrete PIL operations.
        """
        from PIL import ImageEnhance, ImageFilter
        import numpy as np

        enhanced = img.copy()
        if enhanced.mode != 'RGB':
            enhanced = enhanced.convert('RGB')

        for imp in improvements:
            imp_lower = imp.lower()
            intensity = self._parse_intensity(imp)

            # Brightness / exposure
            if any(kw in imp_lower for kw in ('brightness', 'exposure', 'lighter', 'lift shadow', 'raise shadow', 'raise black')):
                factor = 1.0 + (0.15 * intensity)
                if any(kw in imp_lower for kw in ('decrease', 'reduce', 'darker', 'lower', 'down')):
                    factor = 1.0 - (0.12 * intensity)
                enhanced = ImageEnhance.Brightness(enhanced).enhance(factor)

            # Contrast / S-curve / tonal range
            elif any(kw in imp_lower for kw in ('contrast', 's-curve', 'tonal', 'midtone')):
                factor = 1.0 + (0.18 * intensity)
                if any(kw in imp_lower for kw in ('decrease', 'reduce', 'soften', 'flatten')):
                    factor = 1.0 - (0.15 * intensity)
                enhanced = ImageEnhance.Contrast(enhanced).enhance(factor)

            # Saturation / vibrance / color boost
            elif any(kw in imp_lower for kw in ('saturation', 'vibrance', 'vibrant', 'desaturate', 'color')):
                factor = 1.0 + (0.18 * intensity)
                if any(kw in imp_lower for kw in ('desaturate', 'decrease', 'reduce', 'muted', 'mute')):
                    factor = 1.0 - (0.15 * intensity)
                enhanced = ImageEnhance.Color(enhanced).enhance(factor)

            # Sharpness / clarity / detail
            elif any(kw in imp_lower for kw in ('sharp', 'clarity', 'detail', 'crisp')):
                factor = 1.0 + (0.25 * intensity)
                enhanced = ImageEnhance.Sharpness(enhanced).enhance(factor)

            # White balance / color temperature
            elif any(kw in imp_lower for kw in ('white balance', 'temperature', 'warm', 'cool', 'tint')):
                try:
                    arr = np.array(enhanced, dtype=np.float32)
                    shift = 8.0 * intensity
                    if any(kw in imp_lower for kw in ('warm', 'warmer')):
                        arr[:, :, 0] = np.clip(arr[:, :, 0] + shift, 0, 255)      # red up
                        arr[:, :, 2] = np.clip(arr[:, :, 2] - shift * 0.6, 0, 255) # blue down
                    elif any(kw in imp_lower for kw in ('cool', 'cooler')):
                        arr[:, :, 2] = np.clip(arr[:, :, 2] + shift, 0, 255)      # blue up
                        arr[:, :, 0] = np.clip(arr[:, :, 0] - shift * 0.6, 0, 255) # red down
                    enhanced = Image.fromarray(arr.astype(np.uint8))
                except ImportError:
                    pass  # numpy not available, skip

            # Highlight recovery
            elif any(kw in imp_lower for kw in ('highlight', 'recover highlight', 'reduce highlight')):
                try:
                    arr = np.array(enhanced, dtype=np.float32)
                    mask = arr.max(axis=2) > 200
                    reduction = 0.08 * intensity
                    arr[mask] = arr[mask] * (1.0 - reduction)
                    enhanced = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
                except ImportError:
                    pass

            # Shadow recovery / lift shadows
            elif any(kw in imp_lower for kw in ('shadow', 'dark area', 'black point')):
                try:
                    arr = np.array(enhanced, dtype=np.float32)
                    luminance = arr.mean(axis=2)
                    mask = luminance < 60
                    boost = 12.0 * intensity
                    for c in range(3):
                        arr[:, :, c][mask] = np.clip(arr[:, :, c][mask] + boost, 0, 255)
                    enhanced = Image.fromarray(arr.astype(np.uint8))
                except ImportError:
                    # Fall back to simple brightness boost
                    enhanced = ImageEnhance.Brightness(enhanced).enhance(1.0 + 0.08 * intensity)

            # Noise reduction (approximate with gentle blur)
            elif any(kw in imp_lower for kw in ('noise', 'grain', 'denoise')):
                if intensity > 1.0:
                    enhanced = enhanced.filter(ImageFilter.GaussianBlur(radius=1.0))
                else:
                    enhanced = enhanced.filter(ImageFilter.GaussianBlur(radius=0.5))

            # Vignette
            elif 'vignette' in imp_lower:
                try:
                    arr = np.array(enhanced, dtype=np.float32)
                    h, w = arr.shape[:2]
                    Y, X = np.ogrid[:h, :w]
                    cx, cy = w / 2, h / 2
                    dist = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2)
                    max_dist = np.sqrt(cx ** 2 + cy ** 2)
                    vignette = 1.0 - (0.3 * intensity * (dist / max_dist) ** 2)
                    for c in range(3):
                        arr[:, :, c] = np.clip(arr[:, :, c] * vignette, 0, 255)
                    enhanced = Image.fromarray(arr.astype(np.uint8))
                except ImportError:
                    pass

            # Dehaze
            elif any(kw in imp_lower for kw in ('dehaze', 'haze', 'clarity')):
                enhanced = ImageEnhance.Contrast(enhanced).enhance(1.0 + 0.12 * intensity)
                enhanced = ImageEnhance.Color(enhanced).enhance(1.0 + 0.08 * intensity)

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
