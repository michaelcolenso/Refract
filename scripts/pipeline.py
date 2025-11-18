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
from critic import PhotoCritic
from editor import PhotoEditor
from generator import SiteGenerator


class RefractPipeline:
    """Main pipeline orchestrator."""

    def __init__(self, repo_root: Path):
        """Initialize the pipeline."""
        self.repo_root = repo_root
        self.inbox_dir = repo_root / 'inbox'
        self.api_key = os.getenv('GEMINI_API_KEY')

        if not self.api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set")

        # Initialize components
        self.critic = PhotoCritic(self.api_key)
        self.editor = PhotoEditor(self.api_key)
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
            # STEP 1: CRITIC - Analyze the photograph
            print("STEP 1: Analyzing photograph...")
            critique = self.critic.analyze(image_path)

            print(f"  Score: {critique['score']}/100")
            print(f"  Improvements: {len(critique['improvements'])}")
            for i, improvement in enumerate(critique['improvements'], 1):
                print(f"    {i}. {improvement}")
            print(f"  Notes: {critique['notes']}\n")

            # STEP 2: EDITOR - Apply improvements
            print("STEP 2: Applying improvements...")

            # Create temporary edited image
            edited_path = image_path.parent / f"edited_{image_path.name}"

            success = self.editor.edit(image_path, critique['improvements'], edited_path)

            if not success:
                print("  Error: Failed to edit image")
                return False

            print(f"  Image edited successfully\n")

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
