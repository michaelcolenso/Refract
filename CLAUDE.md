# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

REFRACT (REcursive Feedback for Refined Artistic Capture Transformation) is an automated photography improvement pipeline that uses multiple LLM vision APIs to analyze, critique, and enhance photographs. Photos dropped in `inbox/` are processed via GitHub Actions, with results committed back and deployed to GitHub Pages.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Set up environment (copy and edit with your API keys)
cp .env.example .env

# Run the full pipeline locally
cd scripts && python pipeline.py

# Run in dry-run mode (analyze only, no edits or archiving)
cd scripts && python pipeline.py --dry-run

# Test individual components
python scripts/multi_critic.py <image_path>              # Multi-LLM critique
python scripts/editor.py <image> '<improvements_json>' <output>
python scripts/generator.py build                        # Rebuild static site (incremental)
python scripts/generator.py build --full                 # Rebuild static site (full)
python scripts/generator.py create <original> <edited> '<metadata_json>'

# Local development server
python scripts/serve.py                   # Serve at http://localhost:8000
python scripts/serve.py -p 3000 -v        # Custom port, verbose logging

# Run tests
pytest tests/
```

## Architecture

### Pipeline Flow
```
inbox/ → Validate → MultiCritic → Editor → Generator → processed/ + site/public/
```

### Core Components (`scripts/`)

- **`pipeline.py`** - Main orchestrator. Validates images, processes in parallel (max 3 workers), supports --dry-run mode, handles HEIC/WebP formats
- **`multi_critic.py`** - Multi-LLM analysis engine. Submits photos to Gemini, GPT-4o, and Claude for diverse critiques, calculates consensus score, deduplicates improvements
- **`editor.py`** - Applies improvements using Gemini image generation with PIL fallback for reliability
- **`generator.py`** - Creates permanent records in `processed/` and rebuilds Jinja2 static site with incremental build support
- **`serve.py`** - Local development server for previewing the generated site
- **`utils.py`** - Shared utilities including retry_with_backoff decorator

### Key Design Patterns

**Multi-LLM Critic Architecture** (`multi_critic.py`): Abstract `BaseCritic` class with concrete implementations for each provider. Each critic implements `analyze()` and shares `_get_prompt()` and `_parse_response()` from base class.

**Retry with Backoff** (`utils.py`): Shared decorator for API calls that handles rate limits and transient errors with exponential backoff.

**Progressive Fallback** (`editor.py`): Primary Gemini image generation falls back to PIL-based enhancements (brightness, contrast, saturation, sharpness) if API fails.

**Incremental Builds** (`generator.py`): Only regenerates HTML/images for new entries; always regenerates index.html.

### Data Flow

1. Images in `inbox/` are detected (`.jpg`, `.jpeg`, `.png`, `.webp`, `.heic`, `.heif`)
2. Images are validated upfront (invalid files reported, skipped)
3. Each image gets analyzed by available LLMs (needs at least one API key)
4. Consensus score is calculated, improvements are deduplicated
5. Editor applies improvements (Gemini generation → PIL fallback)
6. Generator creates `processed/{timestamp}-{id}/` with original, edited, metadata.json
7. Generator rebuilds static site (incrementally by default)
8. Original removed from inbox

### Output Structure
```
processed/{YYYYMMDD-HHMMSS-xxxx}/
├── original.jpg
├── edited.jpg
└── metadata.json   # Contains score, improvements, notes, critiques array

site/public/
├── index.html      # Gallery (Jinja2 from templates/index.html)
├── {entry-id}.html # Entry pages with interactive before/after slider
├── style.css
└── images/         # Copies with comparison images
```

## Environment Variables

Required (at least one for critique):
- `GEMINI_API_KEY` - Also required for image editing
- `OPENAI_API_KEY` - Optional, for GPT-4o critique
- `ANTHROPIC_API_KEY` - Optional, for Claude critique

For GitHub Actions, set these as repository secrets.

## Supported Image Formats

- JPEG (.jpg, .jpeg)
- PNG (.png)
- WebP (.webp)
- HEIC/HEIF (.heic, .heif) - requires pillow-heif

## GitHub Actions Workflow

`.github/workflows/refract-pipeline.yml` triggers on:
- Push to `main` or `claude/**` branches with changes in `inbox/`, `scripts/`, `site/public/`, or workflows
- Manual dispatch

Two jobs:
1. `process-photos` - Runs pipeline, commits results
2. `deploy-site` - Deploys `site/public/` to GitHub Pages (main branch only)

## Testing

```bash
# Run all tests
pytest tests/

# Run with verbose output
pytest tests/ -v

# Run specific test file
pytest tests/test_utils.py
```

Test files:
- `tests/test_utils.py` - retry_with_backoff decorator tests
- `tests/test_multi_critic.py` - JSON parsing, response validation tests
- `tests/test_generator.py` - entry creation, site building, incremental build tests

## Testing Locally

```bash
# Quick smoke test
cp ~/some-photo.jpg inbox/
python scripts/pipeline.py

# Dry run (analyze without changes)
python scripts/pipeline.py --dry-run

# Verify output
ls processed/
python scripts/serve.py  # View at http://localhost:8000
```
