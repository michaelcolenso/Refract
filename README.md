# REFRACT

**RE**cursive **F**eedback for **R**efined **A**rtistic **C**apture **T**ransformation

An automated photography improvement pipeline powered by multi-LLM analysis. Drop photos into a folder, push to GitHub, and watch as AI transforms them into enhanced images.

## Quick Start

### 1. Set Up API Keys

Add to GitHub Secrets (Settings > Secrets and variables > Actions):

| Secret | Required | Description |
|--------|----------|-------------|
| `GEMINI_API_KEY` | At least one | Google Gemini (critique + editing) |
| `OPENAI_API_KEY` | At least one | OpenAI GPT-4o (critique only) |
| `ANTHROPIC_API_KEY` | At least one | Anthropic Claude (critique only) |

Get keys: [Google AI Studio](https://makersuite.google.com/app/apikey) | [OpenAI](https://platform.openai.com/api-keys) | [Anthropic](https://console.anthropic.com/)

### 2. Enable GitHub Pages

Settings > Pages > Source: **GitHub Actions**

### 3. Process Photos

```bash
cp ~/Photos/my-photo.jpg inbox/
git add inbox/ && git commit -m "Add photos" && git push
```

Your site: `https://YOUR-USERNAME.github.io/YOUR-REPO-NAME/`

## How It Works

```
inbox/ --> Multi-LLM Critique --> Editor --> Generator --> GitHub Pages
           (Gemini/GPT-4o/Claude)  (Gemini)   (Jinja2)
```

1. **Multi-Critic**: Analyzes photos with available LLMs, calculates consensus score, deduplicates improvements
2. **Editor**: Applies improvements using Gemini image generation (with PIL fallback)
3. **Generator**: Creates permanent records in `processed/` and rebuilds static site

## Local Development

```bash
pip install -r requirements.txt
cp .env.example .env  # Add your API keys
python scripts/pipeline.py
python scripts/serve.py  # Preview at http://localhost:8000
```

### CLI Options

```bash
python scripts/pipeline.py              # Process all images in inbox/
python scripts/pipeline.py --dry-run    # Analyze only, don't edit or archive
```

### Image Editing Configuration

REFRACT uses Gemini image generation for edits. By default it uses **Pro** for
all edits. You can override this behavior via environment variables:

```bash
GEMINI_IMAGE_MODEL_POLICY=pro    # pro | flash
GEMINI_IMAGE_MODEL=gemini-2.5-flash-image   # explicit override
GEMINI_IMAGE_SIZE=2K            # Pro-only: 1K, 2K, 4K
GEMINI_IMAGE_ASPECT_RATIO=auto  # or 1:1, 4:3, 16:9, etc
GEMINI_IMAGE_PASSES=1           # number of edit passes
```

### Test Individual Components

```bash
python scripts/multi_critic.py image.jpg                    # Multi-LLM critique
python scripts/editor.py image.jpg '["boost contrast"]' out.jpg
python scripts/generator.py build                           # Rebuild site
```

## Supported Formats

- JPEG (.jpg, .jpeg)
- PNG (.png)
- WebP (.webp)
- HEIC/HEIF (.heic, .heif)

## Repository Structure

```
inbox/              # Drop zone for new photos
processed/          # Permanent records with metadata
site/
  templates/        # Jinja2 templates
  public/           # Generated static site
scripts/
  pipeline.py       # Main orchestrator
  multi_critic.py   # Multi-LLM analysis engine
  editor.py         # Image enhancement
  generator.py      # Site builder
  serve.py          # Local dev server
  utils.py          # Shared utilities
tests/              # Test suite
```

## License

See LICENSE file for details.
