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

from utils import retry_with_backoff


class PhotoEditor:
    """Applies improvements to photographs using Gemini's image editing capabilities."""

    def __init__(self, api_key: str):
        """Initialize the Editor with Gemini API credentials."""
        self.client = genai.Client(api_key=api_key)
        # Using Gemini 3 Pro Preview for image editing
        self.model_name = 'gemini-3-pro-preview'

    def _build_edit_prompt(
        self,
        improvements: List[str],
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Build a detailed editing prompt with context awareness."""

        # Format improvements list
        improvements_text = "\n".join(f"  • {imp}" for imp in improvements)

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

        prompt = f"""You are a professional photo retoucher applying targeted edits to enhance this photograph. Work like an expert using Lightroom/Photoshop—make precise, natural adjustments that improve the image while respecting its artistic intent.

{context_section}REQUESTED EDITS:
{improvements_text}

{preserve_section}EDITING PRINCIPLES:

1. INTENSITY GUIDE (indicated in brackets):
   • [SUBTLE] = Minor refinement, barely noticeable (5-15% adjustment)
   • [MODERATE] = Clear improvement, still natural (15-30% adjustment)
   • [SIGNIFICANT] = Strong correction needed (30-50% adjustment)

2. TECHNICAL STANDARDS:
   • Maintain natural color relationships—avoid oversaturation or color casts
   • Preserve detail in highlights and shadows—no clipping
   • Keep noise levels appropriate to the image
   • Ensure smooth tonal gradations without banding
   • Maintain sharpness without halos or artifacts

3. QUALITY TARGETS:
   • The edit should look professional but not over-processed
   • Someone viewing before/after should think "that's better" not "that's different"
   • Edits should be invisible—the photo should look naturally good
{genre_guidelines}
Generate the enhanced version of this photograph with the requested edits applied."""

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
