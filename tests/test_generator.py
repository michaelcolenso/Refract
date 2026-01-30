"""Tests for generator module."""

import sys
import json
import tempfile
import shutil
from pathlib import Path

import pytest
from PIL import Image

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

from generator import SiteGenerator


@pytest.fixture
def temp_repo():
    """Create a temporary repository structure for testing."""
    temp_dir = Path(tempfile.mkdtemp())

    # Create directory structure
    (temp_dir / 'inbox').mkdir()
    (temp_dir / 'processed').mkdir()
    (temp_dir / 'site' / 'templates').mkdir(parents=True)
    (temp_dir / 'site' / 'public').mkdir(parents=True)

    # Create minimal templates
    index_template = """<!DOCTYPE html>
<html>
<head><title>REFRACT</title></head>
<body>
<h1>Gallery</h1>
{% for entry in entries %}
<div>{{ entry.entry_id }}</div>
{% endfor %}
</body>
</html>"""

    entry_template = """<!DOCTYPE html>
<html>
<head><title>{{ entry.original_filename }}</title></head>
<body>
<h1>{{ entry.entry_id }}</h1>
<p>Score: {{ entry.score }}</p>
</body>
</html>"""

    (temp_dir / 'site' / 'templates' / 'index.html').write_text(index_template)
    (temp_dir / 'site' / 'templates' / 'entry.html').write_text(entry_template)
    (temp_dir / 'site' / 'templates' / 'style.css').write_text("/* test */")

    yield temp_dir

    # Cleanup
    shutil.rmtree(temp_dir)


@pytest.fixture
def test_image(temp_repo):
    """Create a test image file."""
    img = Image.new('RGB', (100, 100), color='red')
    img_path = temp_repo / 'test_original.jpg'
    img.save(img_path)
    return img_path


@pytest.fixture
def edited_image(temp_repo):
    """Create an edited test image file."""
    img = Image.new('RGB', (100, 100), color='blue')
    img_path = temp_repo / 'test_edited.jpg'
    img.save(img_path)
    return img_path


class TestSiteGenerator:
    """Tests for the SiteGenerator class."""

    def test_init_creates_jinja_env(self, temp_repo):
        """Generator should initialize Jinja2 environment."""
        generator = SiteGenerator(temp_repo)

        assert generator.jinja_env is not None
        assert generator.processed_dir == temp_repo / 'processed'
        assert generator.public_dir == temp_repo / 'site' / 'public'

    def test_create_entry(self, temp_repo, test_image, edited_image):
        """create_entry should create entry directory with files."""
        generator = SiteGenerator(temp_repo)

        metadata = {
            "score": 85,
            "improvements": ["Test improvement"],
            "notes": "Test notes"
        }

        entry_dir = generator.create_entry(test_image, edited_image, metadata)

        # Entry directory should exist
        assert entry_dir.exists()
        assert entry_dir.parent == temp_repo / 'processed'

        # Should contain expected files
        assert (entry_dir / 'original.jpg').exists()
        assert (entry_dir / 'edited.jpg').exists()
        assert (entry_dir / 'metadata.json').exists()

        # Metadata should be valid JSON with expected fields
        with open(entry_dir / 'metadata.json') as f:
            saved_metadata = json.load(f)

        assert saved_metadata['score'] == 85
        assert saved_metadata['improvements'] == ["Test improvement"]
        assert 'timestamp' in saved_metadata
        assert 'entry_id' in saved_metadata
        assert saved_metadata['original_filename'] == test_image.name

    def test_create_entry_unique_ids(self, temp_repo, test_image, edited_image):
        """Each entry should have a unique ID."""
        generator = SiteGenerator(temp_repo)

        metadata = {"score": 80, "improvements": [], "notes": ""}

        entry1 = generator.create_entry(test_image, edited_image, metadata)
        entry2 = generator.create_entry(test_image, edited_image, metadata)

        assert entry1.name != entry2.name

    def test_get_all_entries_empty(self, temp_repo):
        """get_all_entries should return empty list when no entries."""
        generator = SiteGenerator(temp_repo)

        entries = generator.get_all_entries()

        assert entries == []

    def test_get_all_entries_with_entries(self, temp_repo, test_image, edited_image):
        """get_all_entries should return all processed entries."""
        generator = SiteGenerator(temp_repo)

        metadata = {"score": 80, "improvements": [], "notes": ""}

        generator.create_entry(test_image, edited_image, metadata)
        generator.create_entry(test_image, edited_image, metadata)

        entries = generator.get_all_entries()

        assert len(entries) == 2

    def test_get_all_entries_sorted_reverse(self, temp_repo, test_image, edited_image):
        """Entries should be sorted newest first."""
        generator = SiteGenerator(temp_repo)

        metadata = {"score": 80, "improvements": [], "notes": ""}

        entry1 = generator.create_entry(test_image, edited_image, metadata)
        entry2 = generator.create_entry(test_image, edited_image, metadata)

        entries = generator.get_all_entries()

        # Entry2 was created second, should be first in list
        assert entries[0]['entry_id'] == entry2.name

    def test_build_site_creates_index(self, temp_repo, test_image, edited_image):
        """build_site should create index.html."""
        generator = SiteGenerator(temp_repo)

        metadata = {"score": 80, "improvements": [], "notes": ""}
        generator.create_entry(test_image, edited_image, metadata)
        generator.build_site()

        assert (temp_repo / 'site' / 'public' / 'index.html').exists()

    def test_build_site_creates_entry_pages(self, temp_repo, test_image, edited_image):
        """build_site should create individual entry pages."""
        generator = SiteGenerator(temp_repo)

        metadata = {"score": 80, "improvements": [], "notes": ""}
        entry_dir = generator.create_entry(test_image, edited_image, metadata)
        generator.build_site()

        entry_page = temp_repo / 'site' / 'public' / f"{entry_dir.name}.html"
        assert entry_page.exists()

    def test_build_site_copies_css(self, temp_repo, test_image, edited_image):
        """build_site should copy CSS to public directory."""
        generator = SiteGenerator(temp_repo)

        generator.build_site()

        assert (temp_repo / 'site' / 'public' / 'style.css').exists()

    def test_build_site_copies_images(self, temp_repo, test_image, edited_image):
        """build_site should copy images to public/images."""
        generator = SiteGenerator(temp_repo)

        metadata = {"score": 80, "improvements": [], "notes": ""}
        entry_dir = generator.create_entry(test_image, edited_image, metadata)
        generator.build_site()

        images_dir = temp_repo / 'site' / 'public' / 'images'
        assert images_dir.exists()

        # Should have original, edited, and comparison images
        image_files = list(images_dir.glob('*'))
        assert len(image_files) >= 3

    def test_build_site_creates_comparison_image(self, temp_repo, test_image, edited_image):
        """build_site should create comparison images."""
        generator = SiteGenerator(temp_repo)

        metadata = {"score": 80, "improvements": [], "notes": ""}
        entry_dir = generator.create_entry(test_image, edited_image, metadata)
        generator.build_site()

        comparison_files = list((temp_repo / 'site' / 'public' / 'images').glob('*-comparison.jpg'))
        assert len(comparison_files) == 1

    def test_create_comparison_image(self, temp_repo, test_image, edited_image):
        """create_comparison_image should create valid image."""
        generator = SiteGenerator(temp_repo)

        output_path = temp_repo / 'comparison.jpg'
        generator.create_comparison_image(test_image, edited_image, output_path)

        assert output_path.exists()

        # Should be a valid image
        img = Image.open(output_path)
        assert img.height == 800  # Target height
        assert img.width > 200  # At least two images side by side


class TestReReview:
    """Tests for re-review data handling."""

    def test_entry_with_re_review_metadata(self, temp_repo, test_image, edited_image):
        """create_entry should store re-review data in metadata."""
        generator = SiteGenerator(temp_repo)

        metadata = {
            "score": 65,
            "consensus_score": 65.0,
            "improvements": ["[MODERATE] Boost contrast"],
            "combined_improvements": ["[MODERATE] Boost contrast"],
            "notes": "Original notes",
            "critiques": [
                {"llm": "gemini", "score": 65.0, "improvements": ["[MODERATE] Boost contrast"], "notes": "Needs work"}
            ],
            "re_review": {
                "critiques": [
                    {"llm": "gemini", "score": 78.0, "improvements": ["[SUBTLE] Fine-tune highlights"], "notes": "Much improved"}
                ],
                "consensus_score": 78.0,
                "score": 78.0,
                "notes": "[GEMINI] Much improved",
                "summary": "[GEMINI] Much improved",
                "context": {},
                "score_delta": 13.0,
            }
        }

        entry_dir = generator.create_entry(test_image, edited_image, metadata)

        with open(entry_dir / 'metadata.json') as f:
            saved = json.load(f)

        assert 're_review' in saved
        assert saved['re_review']['consensus_score'] == 78.0
        assert saved['re_review']['score_delta'] == 13.0
        assert len(saved['re_review']['critiques']) == 1

    def test_build_site_cleans_re_review_improvements(self, temp_repo, test_image, edited_image):
        """build_site should clean severity tags from re-review critique improvements."""
        generator = SiteGenerator(temp_repo)

        metadata = {
            "score": 60,
            "consensus_score": 60.0,
            "improvements": ["[MODERATE] Boost contrast"],
            "combined_improvements": ["[MODERATE] Boost contrast"],
            "notes": "Test",
            "critiques": [
                {"llm": "gemini", "score": 60.0, "improvements": ["[MODERATE] Boost contrast"], "notes": "Needs work"}
            ],
            "re_review": {
                "critiques": [
                    {"llm": "gemini", "score": 75.0, "improvements": ["[SUBTLE] Fine-tune highlights"], "notes": "Improved"}
                ],
                "consensus_score": 75.0,
                "score": 75.0,
                "notes": "[GEMINI] Improved",
                "summary": "[GEMINI] Improved",
                "context": {},
                "score_delta": 15.0,
            }
        }

        generator.create_entry(test_image, edited_image, metadata)
        generator.build_site()

        entries = generator.get_all_entries()
        assert len(entries) == 1

        # The re-review data should be preserved in the stored metadata
        entry = entries[0]
        assert 're_review' in entry
        assert entry['re_review']['score_delta'] == 15.0

    def test_build_site_without_re_review(self, temp_repo, test_image, edited_image):
        """build_site should work when no re-review data is present."""
        generator = SiteGenerator(temp_repo)

        metadata = {
            "score": 80,
            "improvements": ["Test improvement"],
            "notes": "No re-review"
        }

        generator.create_entry(test_image, edited_image, metadata)
        generator.build_site()

        entries = generator.get_all_entries()
        assert len(entries) == 1
        assert entries[0].get('re_review') is None


class TestIncrementalBuilds:
    """Tests for incremental build functionality."""

    def test_incremental_build_skips_existing(self, temp_repo, test_image, edited_image):
        """Incremental build should skip already-built entries."""
        generator = SiteGenerator(temp_repo)

        metadata = {"score": 80, "improvements": [], "notes": ""}
        entry_dir = generator.create_entry(test_image, edited_image, metadata)

        # First build
        generator.build_site()

        # Modify the entry page to detect if it's regenerated
        entry_page = temp_repo / 'site' / 'public' / f"{entry_dir.name}.html"
        entry_page.write_text("MODIFIED")

        # Second build (incremental)
        generator.build_site()

        # Entry page should still be modified (not regenerated)
        assert entry_page.read_text() == "MODIFIED"

    def test_full_build_regenerates_all(self, temp_repo, test_image, edited_image):
        """Full build should regenerate all entries."""
        generator = SiteGenerator(temp_repo)

        metadata = {"score": 80, "improvements": [], "notes": ""}
        entry_dir = generator.create_entry(test_image, edited_image, metadata)

        # First build
        generator.build_site()

        # Modify the entry page
        entry_page = temp_repo / 'site' / 'public' / f"{entry_dir.name}.html"
        entry_page.write_text("MODIFIED")

        # Full rebuild
        generator.build_site(force_full=True)

        # Entry page should be regenerated (not modified)
        assert entry_page.read_text() != "MODIFIED"

    def test_index_always_regenerated(self, temp_repo, test_image, edited_image):
        """Index page should always be regenerated."""
        generator = SiteGenerator(temp_repo)

        metadata = {"score": 80, "improvements": [], "notes": ""}
        generator.create_entry(test_image, edited_image, metadata)

        # First build
        generator.build_site()

        # Modify index
        index_page = temp_repo / 'site' / 'public' / 'index.html'
        index_page.write_text("MODIFIED")

        # Second build (incremental)
        generator.build_site()

        # Index should be regenerated
        assert index_page.read_text() != "MODIFIED"
