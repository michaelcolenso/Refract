#!/usr/bin/env python3
"""
REFRACT Generator - Documentation and Site Builder
Creates permanent records and regenerates the static website.
"""

import os
import sys
import json
import shutil
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Set
from jinja2 import Environment, FileSystemLoader
from PIL import Image


class SiteGenerator:
    """Generates documentation and rebuilds the static website."""

    _IMPROVEMENT_TAG_RE = re.compile(r"^\s*\[(subtle|moderate|significant|strong|major|minor|severe|light|heavy)\]\s*", re.IGNORECASE)

    def __init__(self, repo_root: Path):
        """Initialize the generator."""
        self.repo_root = repo_root
        self.processed_dir = repo_root / 'processed'
        self.site_dir = repo_root / 'site'
        self.templates_dir = self.site_dir / 'templates'
        self.public_dir = self.site_dir / 'public'

        # Setup Jinja2
        self.jinja_env = Environment(loader=FileSystemLoader(str(self.templates_dir)))

    def create_entry(self, original_path: Path, edited_path: Path, metadata: Dict[str, Any]) -> Path:
        """
        Create a permanent entry for a processed photograph.

        Args:
            original_path: Path to original image
            edited_path: Path to edited image
            metadata: Critic's analysis (score, improvements, notes)

        Returns:
            Path to the created entry directory
        """
        # Generate unique entry ID
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        entry_id = f"{timestamp}-{os.urandom(4).hex()}"
        entry_dir = self.processed_dir / entry_id

        # Create entry directory
        entry_dir.mkdir(parents=True, exist_ok=True)

        # Copy images
        original_dest = entry_dir / f"original{original_path.suffix}"
        edited_dest = entry_dir / f"edited{edited_path.suffix}"

        shutil.copy2(original_path, original_dest)
        shutil.copy2(edited_path, edited_dest)

        # Add metadata
        metadata_with_timestamp = {
            **metadata,
            'timestamp': timestamp,
            'entry_id': entry_id,
            'original_filename': original_path.name,
            'original_image': original_dest.name,
            'edited_image': edited_dest.name
        }

        # Save metadata
        metadata_path = entry_dir / 'metadata.json'
        with open(metadata_path, 'w') as f:
            json.dump(metadata_with_timestamp, f, indent=2)

        print(f"Created entry: {entry_id}")
        return entry_dir

    def create_comparison_image(self, original_path: Path, edited_path: Path, output_path: Path):
        """Create a side-by-side comparison image."""
        original = Image.open(original_path)
        edited = Image.open(edited_path)

        # Resize to same height
        target_height = 800
        original_aspect = original.width / original.height
        edited_aspect = edited.width / edited.height

        original_resized = original.resize(
            (int(target_height * original_aspect), target_height),
            Image.Resampling.LANCZOS
        )
        edited_resized = edited.resize(
            (int(target_height * edited_aspect), target_height),
            Image.Resampling.LANCZOS
        )

        # Create comparison
        total_width = original_resized.width + edited_resized.width + 10
        comparison = Image.new('RGB', (total_width, target_height), 'white')

        comparison.paste(original_resized, (0, 0))
        comparison.paste(edited_resized, (original_resized.width + 10, 0))

        comparison.save(output_path, quality=90)

    def get_all_entries(self) -> List[Dict[str, Any]]:
        """Load all processed entries."""
        entries = []

        for entry_dir in sorted(self.processed_dir.iterdir(), reverse=True):
            if entry_dir.is_dir() and not entry_dir.name.startswith('.'):
                metadata_path = entry_dir / 'metadata.json'
                if metadata_path.exists():
                    with open(metadata_path) as f:
                        metadata = json.load(f)
                        metadata['path'] = entry_dir
                        entries.append(metadata)

        return entries

    def _clean_improvement_text(self, text: str) -> str:
        """Remove severity tags like [SUBTLE] from improvement text."""
        if not isinstance(text, str):
            return ""
        cleaned = self._IMPROVEMENT_TAG_RE.sub("", text).strip()
        return cleaned

    def _clean_improvement_list(self, improvements: Any) -> List[str]:
        """Normalize and clean improvement lists for display."""
        if not isinstance(improvements, list):
            return []
        cleaned = []
        for item in improvements:
            cleaned_text = self._clean_improvement_text(item)
            if cleaned_text:
                cleaned.append(cleaned_text)
        return cleaned

    def _get_existing_entry_ids(self) -> Set[str]:
        """Get set of entry IDs that already have generated HTML pages."""
        existing = set()
        if not self.public_dir.exists():
            return existing

        for html_file in self.public_dir.glob('*.html'):
            # Skip index.html
            if html_file.name == 'index.html':
                continue
            # Extract entry ID from filename (e.g., "20240115-143022-abc12345.html")
            entry_id = html_file.stem
            existing.add(entry_id)

        return existing

    def _get_existing_images(self) -> Set[str]:
        """Get set of image filenames already in public/images."""
        existing = set()
        images_dir = self.public_dir / 'images'
        if not images_dir.exists():
            return existing

        for img_file in images_dir.iterdir():
            if img_file.is_file():
                existing.add(img_file.name)

        return existing

    def build_site(self, force_full: bool = False):
        """
        Rebuild the static website with incremental support.

        Args:
            force_full: If True, regenerate everything. If False, only new entries.
        """
        # Create public directory
        self.public_dir.mkdir(parents=True, exist_ok=True)

        # Get all entries
        entries = self.get_all_entries()

        # Determine what already exists (for incremental builds)
        existing_entry_ids = set() if force_full else self._get_existing_entry_ids()
        existing_images = set() if force_full else self._get_existing_images()

        # Copy images to public
        images_dir = self.public_dir / 'images'
        images_dir.mkdir(exist_ok=True)

        new_entries = 0
        skipped_entries = 0

        for entry in entries:
            entry_dir = entry['path']
            entry_id = entry['entry_id']

            # Add display-friendly improvements without severity tags
            entry['improvements_display'] = self._clean_improvement_list(entry.get('improvements'))
            entry['combined_improvements_display'] = self._clean_improvement_list(
                entry.get('combined_improvements') or entry.get('improvements')
            )
            if entry.get('critiques'):
                for critique in entry['critiques']:
                    critique['improvements_display'] = self._clean_improvement_list(critique.get('improvements'))

            # Clean re-review critique improvements for display
            re_review = entry.get('re_review')
            if re_review and re_review.get('critiques'):
                for critique in re_review['critiques']:
                    critique['improvements_display'] = self._clean_improvement_list(critique.get('improvements'))

            # Determine image paths
            original_src = entry_dir / entry['original_image']
            edited_src = entry_dir / entry['edited_image']

            original_dest = images_dir / f"{entry_id}-original{original_src.suffix}"
            edited_dest = images_dir / f"{entry_id}-edited{edited_src.suffix}"
            comparison_dest = images_dir / f"{entry_id}-comparison.jpg"

            # Check if this entry needs processing
            is_new = entry_id not in existing_entry_ids

            # Copy images (check each individually)
            if is_new or original_dest.name not in existing_images:
                shutil.copy2(original_src, original_dest)

            if is_new or edited_dest.name not in existing_images:
                shutil.copy2(edited_src, edited_dest)

            # Create comparison image if needed
            if is_new or comparison_dest.name not in existing_images:
                self.create_comparison_image(original_src, edited_src, comparison_dest)

            # Update entry with web paths (needed for templates)
            entry['web_original'] = f"images/{original_dest.name}"
            entry['web_edited'] = f"images/{edited_dest.name}"
            entry['web_comparison'] = f"images/{comparison_dest.name}"

            # Generate entry page if new
            if is_new:
                entry_template = self.jinja_env.get_template('entry.html')
                entry_html = entry_template.render(entry=entry)
                entry_page = self.public_dir / f"{entry_id}.html"

                with open(entry_page, 'w') as f:
                    f.write(entry_html)
                new_entries += 1
            else:
                skipped_entries += 1

        # Always regenerate index page (shows all entries)
        template = self.jinja_env.get_template('index.html')
        index_html = template.render(entries=entries, total=len(entries))

        with open(self.public_dir / 'index.html', 'w') as f:
            f.write(index_html)

        # Copy CSS
        css_src = self.templates_dir / 'style.css'
        css_dest = self.public_dir / 'style.css'
        if css_src.exists():
            shutil.copy2(css_src, css_dest)

        # Copy favicon assets if present
        for favicon_name in ("favicon.ico", "favicon.png", "apple-touch-icon.png"):
            favicon_src = self.templates_dir / favicon_name
            if favicon_src.exists():
                shutil.copy2(favicon_src, self.public_dir / favicon_name)

        if new_entries > 0:
            print(f"Site built: {new_entries} new entries, {skipped_entries} unchanged")
        else:
            print(f"Site built successfully: {len(entries)} entries (all unchanged)")


def main():
    """CLI interface for the Generator."""
    repo_root = Path(__file__).parent.parent

    if len(sys.argv) < 2:
        print("Usage: generator.py <command> [args]", file=sys.stderr)
        print("\nCommands:", file=sys.stderr)
        print("  create <original> <edited> <metadata_json>  - Create new entry", file=sys.stderr)
        print("  build                                        - Rebuild site (incremental)", file=sys.stderr)
        print("  build --full                                 - Rebuild site (full)", file=sys.stderr)
        sys.exit(1)

    command = sys.argv[1]
    generator = SiteGenerator(repo_root)

    if command == 'create':
        if len(sys.argv) != 5:
            print("Usage: generator.py create <original> <edited> <metadata_json>", file=sys.stderr)
            sys.exit(1)

        original_path = Path(sys.argv[2])
        edited_path = Path(sys.argv[3])
        metadata_json = sys.argv[4]

        # Parse metadata
        metadata = json.loads(metadata_json)

        # Create entry
        entry_dir = generator.create_entry(original_path, edited_path, metadata)
        print(f"Entry created: {entry_dir}")

    elif command == 'build':
        force_full = '--full' in sys.argv
        generator.build_site(force_full=force_full)

    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
