#!/usr/bin/env python3
"""
REFRACT Pipeline - Main Orchestrator
Coordinates the Critic, Editor, and Generator to process photographs.
"""

import os
import sys
import json
from pathlib import Path
from typing import List
import traceback

# Import our modules
from multi_critic import MultiCritic
from editor import PhotoEditor
from generator import SiteGenerator


class RefractPipeline:
    """Main pipeline orchestrator."""

    def __init__(self, repo_root: Path):
        """Initialize the pipeline."""
        self.repo_root = repo_root
        self.inbox_dir = repo_root / 'inbox'

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
        if self.gemini_key:
            self.editor = PhotoEditor(self.gemini_key)
        else:
            self.editor = None
            print("  Warning: No GEMINI_API_KEY - image editing disabled")

        self.generator = SiteGenerator(repo_root)

    def get_new_images(self) -> List[Path]:
        """Find all images in the inbox."""
        if not self.inbox_dir.exists():
            return []

        image_extensions = {'.jpg', '.jpeg', '.png', '.JPG', '.JPEG', '.PNG'}
        images = []

        for file_path in self.inbox_dir.iterdir():
            if file_path.is_file() and file_path.suffix in image_extensions:
                # Skip hidden files and .gitkeep
                if not file_path.name.startswith('.'):
                    images.append(file_path)

        return sorted(images)

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

            # STEP 2: EDITOR - Apply improvements
            print("STEP 2: Applying improvements...")

            # Create temporary edited image
            edited_path = image_path.parent / f"edited_{image_path.name}"

            if self.editor:
                success = self.editor.edit(image_path, critique['improvements'], edited_path)

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

            # STEP 3: GENERATOR - Create entry and update site
            print("STEP 3: Creating documentation...")

            entry_dir = self.generator.create_entry(image_path, edited_path, critique)
            print(f"  Entry created: {entry_dir.name}\n")

            # Clean up temporary edited image
            if edited_path.exists():
                edited_path.unlink()

            # Archive the original from inbox
            print("STEP 4: Archiving original...")
            image_path.unlink()
            print(f"  Removed from inbox: {image_path.name}\n")

            print(f"✓ Successfully processed: {image_path.name}")
            return True

        except Exception as e:
            print(f"✗ Error processing {image_path.name}: {e}", file=sys.stderr)
            traceback.print_exc()
            return False

    def run(self):
        """Run the complete pipeline."""
        print("\n" + "="*60)
        print("REFRACT - Automated Photography Improvement Pipeline")
        print("="*60 + "\n")

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

        # Process each image
        successful = 0
        failed = 0

        for image_path in images:
            if self.process_image(image_path):
                successful += 1
            else:
                failed += 1

        # Rebuild site
        print("\n" + "="*60)
        print("Rebuilding static site...")
        print("="*60 + "\n")

        self.generator.build_site()

        # Summary
        print("\n" + "="*60)
        print("Pipeline Summary")
        print("="*60)
        print(f"  Processed: {successful} successful, {failed} failed")
        print(f"  Total entries: {len(self.generator.get_all_entries())}")
        print("="*60 + "\n")


def main():
    """Entry point for the pipeline."""
    repo_root = Path(__file__).parent.parent

    try:
        pipeline = RefractPipeline(repo_root)
        pipeline.run()
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
