#!/usr/bin/env python3
"""
REFRACT Pipeline - Main Orchestrator
Coordinates the Critic, Editor, and Generator to process photographs.
"""

import os
import sys
import json
import argparse
from pathlib import Path
from typing import List, Tuple
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# Import our modules
from multi_critic import MultiCritic
from editor import PhotoEditor
from generator import SiteGenerator

# Register HEIC/HEIF support if available
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    HEIC_SUPPORT = True
except ImportError:
    HEIC_SUPPORT = False


def validate_image(image_path: Path) -> Tuple[bool, str]:
    """
    Validate that an image file is readable and valid.

    Args:
        image_path: Path to the image file

    Returns:
        Tuple of (is_valid, error_message)
    """
    from PIL import Image as PILImage

    try:
        with PILImage.open(image_path) as img:
            img.verify()
        # Re-open to actually load (verify() makes the file unusable)
        with PILImage.open(image_path) as img:
            img.load()
        return True, ""
    except Exception as e:
        return False, str(e)


class RefractPipeline:
    """Main pipeline orchestrator."""

    def __init__(self, repo_root: Path, dry_run: bool = False):
        """Initialize the pipeline."""
        self.repo_root = repo_root
        self.inbox_dir = repo_root / 'inbox'
        self.dry_run = dry_run

        # Get API keys from environment
        self.gemini_key = os.getenv('GEMINI_API_KEY')
        self.openai_key = os.getenv('OPENAI_API_KEY')
        self.anthropic_key = os.getenv('ANTHROPIC_API_KEY')

        if not any([self.gemini_key, self.openai_key, self.anthropic_key]):
            raise ValueError("At least one API key must be set: GEMINI_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY")

        # Initialize components
        print("Initializing Multi-LLM Critics...")
        self.critic = MultiCritic(
            gemini_key=self.gemini_key,
            openai_key=self.openai_key,
            anthropic_key=self.anthropic_key
        )

        # Editor still uses Gemini (requires GEMINI_API_KEY for image generation)
        if self.gemini_key and not self.dry_run:
            self.editor = PhotoEditor(self.gemini_key)
        else:
            self.editor = None
            if not self.dry_run:
                print("  Warning: No GEMINI_API_KEY - image editing disabled")

        if not self.dry_run:
            self.generator = SiteGenerator(repo_root)
        else:
            self.generator = None

        # Thread safety lock for generator operations
        self._lock = threading.Lock()

    def get_new_images(self) -> List[Path]:
        """Find all images in the inbox."""
        if not self.inbox_dir.exists():
            return []

        # Supported image extensions (WebP and HEIC added)
        image_extensions = {
            '.jpg', '.jpeg', '.png', '.webp',
            '.JPG', '.JPEG', '.PNG', '.WEBP'
        }

        # Add HEIC extensions if support is available
        if HEIC_SUPPORT:
            image_extensions.update({'.heic', '.heif', '.HEIC', '.HEIF'})

        images = []

        for file_path in self.inbox_dir.iterdir():
            if file_path.is_file() and file_path.suffix in image_extensions:
                # Skip hidden files and .gitkeep
                if not file_path.name.startswith('.'):
                    images.append(file_path)

        return sorted(images)

    def validate_images(self, images: List[Path]) -> Tuple[List[Path], List[Tuple[Path, str]]]:
        """
        Validate all images before processing.

        Args:
            images: List of image paths to validate

        Returns:
            Tuple of (valid_images, invalid_images_with_errors)
        """
        valid = []
        invalid = []

        for image_path in images:
            is_valid, error = validate_image(image_path)
            if is_valid:
                valid.append(image_path)
            else:
                invalid.append((image_path, error))

        return valid, invalid

    def process_image(self, image_path: Path) -> bool:
        """
        Process a single image through the complete pipeline.

        Args:
            image_path: Path to the image in the inbox

        Returns:
            True if successful, False otherwise
        """
        print(f"\n{'='*60}")
        print(f"Processing: {image_path.name}")
        print(f"{'='*60}\n")

        try:
            # STEP 1: CRITIC - Analyze the photograph with multiple LLMs
            print("STEP 1: Analyzing photograph with multiple LLMs...")
            critique = self.critic.analyze(image_path)

            # Display individual LLM scores
            print("\n  Individual LLM Scores:")
            for c in critique.get('critiques', []):
                if c.get('score') is not None:
                    print(f"    {c['llm'].upper()}: {c['score']}/100")
                else:
                    print(f"    {c['llm'].upper()}: Failed - {c.get('error', 'Unknown error')}")

            print(f"\n  Consensus Score: {critique['consensus_score']}/100")
            print(f"  Combined Improvements: {len(critique['combined_improvements'])}")
            for i, improvement in enumerate(critique['improvements'], 1):
                print(f"    {i}. {improvement}")
            print()

            # If dry run, stop here
            if self.dry_run:
                print("  [DRY RUN] Skipping edit, archive, and site generation")
                return True

            # STEP 2: EDITOR - Apply improvements
            print("STEP 2: Applying improvements...")

            # Create temporary edited image
            edited_path = image_path.parent / f"edited_{image_path.name}"

            if self.editor:
                # Pass context to editor for genre-aware editing
                context = critique.get('context', {})
                success = self.editor.edit(image_path, critique['improvements'], edited_path, context)

                if not success:
                    print("  Warning: Failed to edit image, using original")
                    # Copy original as edited for fallback
                    import shutil
                    shutil.copy(image_path, edited_path)
                else:
                    print(f"  Image edited successfully\n")
            else:
                # No editor available, use original image
                print("  Skipping edits (no GEMINI_API_KEY for editor)")
                import shutil
                shutil.copy(image_path, edited_path)

            # Validate the edited image is a valid image file
            from PIL import Image as PILImage
            try:
                with PILImage.open(edited_path) as test_img:
                    test_img.verify()
                # Re-open to actually load and ensure it's readable
                with PILImage.open(edited_path) as test_img:
                    test_img.load()
            except Exception as validate_err:
                print(f"  Warning: Edited image validation failed ({validate_err}), using original")
                import shutil
                shutil.copy(image_path, edited_path)
                # Convert to ensure proper format
                with PILImage.open(edited_path) as img:
                    if edited_path.suffix.lower() in ['.jpg', '.jpeg']:
                        img = img.convert('RGB')
                    img.save(edited_path, quality=95)

            # STEP 3: RE-REVIEW - Score the edited photograph
            print("STEP 3: Re-reviewing edited photograph...")
            try:
                re_review = self.critic.analyze(edited_path)

                # Display re-review scores
                print("\n  Re-review Scores:")
                for c in re_review.get('critiques', []):
                    if c.get('score') is not None:
                        print(f"    {c['llm'].upper()}: {c['score']}/100")
                    else:
                        print(f"    {c['llm'].upper()}: Failed - {c.get('error', 'Unknown error')}")

                original_score = critique['consensus_score']
                new_score = re_review['consensus_score']
                delta = round(new_score - original_score, 1)
                sign = "+" if delta > 0 else ""
                print(f"\n  Original Score: {original_score}/100")
                print(f"  Re-review Score: {new_score}/100")
                print(f"  Improvement: {sign}{delta} points\n")

                critique['re_review'] = {
                    'critiques': re_review.get('critiques', []),
                    'consensus_score': re_review['consensus_score'],
                    'score': re_review['score'],
                    'notes': re_review.get('notes', ''),
                    'summary': re_review.get('summary', ''),
                    'context': re_review.get('context', {}),
                    'score_delta': delta,
                }
            except Exception as e:
                print(f"  Warning: Re-review failed: {e}")
                print("  Continuing without re-review data.\n")

            # STEP 4: GENERATOR - Create entry and update site
            print("STEP 4: Creating documentation...")

            # Thread-safe entry creation
            with self._lock:
                entry_dir = self.generator.create_entry(image_path, edited_path, critique)
                print(f"  Entry created: {entry_dir.name}\n")

            # Clean up temporary edited image
            if edited_path.exists():
                edited_path.unlink()

            # Archive the original from inbox
            print("STEP 5: Archiving original...")
            image_path.unlink()
            print(f"  Removed from inbox: {image_path.name}\n")

            print(f"Successfully processed: {image_path.name}")
            return True

        except Exception as e:
            print(f"Error processing {image_path.name}: {e}", file=sys.stderr)
            traceback.print_exc()
            return False

    def run(self):
        """Run the complete pipeline."""
        print("\n" + "="*60)
        print("REFRACT - Automated Photography Improvement Pipeline")
        if self.dry_run:
            print("          *** DRY RUN MODE ***")
        print("="*60 + "\n")

        if not HEIC_SUPPORT:
            print("Note: HEIC/HEIF support not available (install pillow-heif)\n")

        # Find new images
        images = self.get_new_images()

        if not images:
            print("No new images found in inbox/")
            print("Add photos to inbox/ and push to trigger processing.\n")
            return

        print(f"Found {len(images)} image(s) to process:\n")
        for img in images:
            print(f"  - {img.name}")
        print()

        # Validate images upfront
        print("Validating images...")
        valid_images, invalid_images = self.validate_images(images)

        if invalid_images:
            print(f"\nWarning: {len(invalid_images)} invalid image(s) found:")
            for img_path, error in invalid_images:
                print(f"  - {img_path.name}: {error}")
            print()

        if not valid_images:
            print("No valid images to process.\n")
            return

        print(f"Processing {len(valid_images)} valid image(s)...\n")

        # Process images in parallel (max 3 concurrent to avoid API rate limits)
        successful = 0
        failed = 0
        max_workers = min(3, len(valid_images))  # Don't create more workers than images

        print(f"Processing with {max_workers} parallel worker(s)...\n")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all image processing tasks
            future_to_image = {
                executor.submit(self.process_image, img): img
                for img in valid_images
            }

            # Process results as they complete
            for future in as_completed(future_to_image):
                image_path = future_to_image[future]
                try:
                    if future.result():
                        successful += 1
                    else:
                        failed += 1
                except Exception as e:
                    print(f"Exception processing {image_path.name}: {e}", file=sys.stderr)
                    traceback.print_exc()
                    failed += 1

        # Rebuild site (unless dry run)
        if not self.dry_run:
            print("\n" + "="*60)
            print("Rebuilding static site...")
            print("="*60 + "\n")

            self.generator.build_site()

        # Summary
        print("\n" + "="*60)
        print("Pipeline Summary")
        print("="*60)
        print(f"  Mode: {'DRY RUN' if self.dry_run else 'FULL'}")
        print(f"  Processed: {successful} successful, {failed} failed")
        if invalid_images:
            print(f"  Skipped: {len(invalid_images)} invalid")
        if not self.dry_run and self.generator:
            print(f"  Total entries: {len(self.generator.get_all_entries())}")
        print("="*60 + "\n")


def main():
    """Entry point for the pipeline."""
    parser = argparse.ArgumentParser(
        description='REFRACT - Automated Photography Improvement Pipeline'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Analyze images only, without editing, archiving, or rebuilding the site'
    )
    args = parser.parse_args()

    repo_root = Path(__file__).parent.parent

    try:
        pipeline = RefractPipeline(repo_root, dry_run=args.dry_run)
        pipeline.run()
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
