# REFRACT

**RE**cursive **F**eedback for **R**efined **A**rtistic **C**apture **T**ransformation

> A self-correcting photography log powered by Google Gemini AI

## Overview

REFRACT is an automated, file-driven photography improvement pipeline that analyzes, enhances, and documents your photographs. Simply drop photos into a folder, push to GitHub, and watch as AI transforms them into professional-quality images.

### How It Works

```
User adds photo → Push to GitHub → Automated Pipeline
                                          ↓
                                    1. CRITIC (Gemini Vision)
                                       Analyzes photo
                                       Scores quality (0-100)
                                       Generates improvements
                                          ↓
                                    2. EDITOR (Gemini Image)
                                       Applies improvements
                                       Enhances the photo
                                          ↓
                                    3. GENERATOR
                                       Creates permanent record
                                       Builds comparison
                                       Updates static site
                                          ↓
                                    4. PUBLICATION
                                       Commits results
                                       Deploys to GitHub Pages
```

## Features

- **Zero-Touch Automation**: Drop photos in `inbox/`, push, done
- **AI-Powered Analysis**: Gemini Vision evaluates composition, lighting, colors
- **Intelligent Editing**: AI applies specific, actionable improvements
- **Permanent Records**: Every photo becomes a documented entry
- **Beautiful Gallery**: Responsive static site with before/after comparisons
- **No External State**: Repository is the database
- **Self-Documenting**: Each entry includes score, improvements, and notes

## Quick Start

### Prerequisites

- GitHub account with this repository
- Google Gemini API key ([Get one here](https://makersuite.google.com/app/apikey))

### Setup

1. **Add your Gemini API key to GitHub Secrets**
   - Go to: Settings → Secrets and variables → Actions
   - Create new secret: `GEMINI_API_KEY`
   - Paste your API key

2. **Enable GitHub Pages**
   - Go to: Settings → Pages
   - Source: GitHub Actions

3. **Start using REFRACT**
   ```bash
   # Add photos to inbox
   cp ~/Photos/my-photo.jpg inbox/

   # Commit and push
   git add inbox/
   git commit -m "Add new photo"
   git push
   ```

4. **Watch the magic happen**
   - GitHub Actions runs automatically
   - Check the "Actions" tab to see progress
   - Visit your GitHub Pages URL to see results

## Repository Structure

```
refract/
├── inbox/              # Drop zone for new photos
│   └── [your-photos]   # Add .jpg, .jpeg, .png files here
│
├── processed/          # Permanent photography records
│   └── {timestamp}-{id}/
│       ├── original.jpg      # Original photograph
│       ├── edited.jpg        # AI-enhanced version
│       └── metadata.json     # Analysis & improvements
│
├── site/               # Static website
│   ├── public/         # Generated site (auto-deployed)
│   └── templates/      # Site templates & styles
│
├── scripts/            # Pipeline automation
│   ├── critic.py       # Gemini Vision analysis
│   ├── editor.py       # Gemini Image editing
│   ├── generator.py    # Site builder
│   └── pipeline.py     # Main orchestrator
│
└── .github/workflows/  # GitHub Actions automation
    └── refract-pipeline.yml
```

## The Pipeline Components

### 1. The Critic (Gemini Vision)

Analyzes photographs and outputs strict JSON:

```json
{
  "score": 85,
  "improvements": [
    "Increase brightness by 15% to enhance overall exposure",
    "Boost vibrance in blue tones to make the sky more dramatic",
    "Apply slight crop to follow rule of thirds composition"
  ],
  "notes": "Well-composed landscape with good subject placement. The exposure is slightly dark and colors could be more vibrant."
}
```

**Evaluation Criteria:**
- Composition and framing
- Lighting and exposure
- Color balance and saturation
- Subject clarity and focus
- Overall artistic impact

### 2. The Editor (Gemini Image)

Applies improvements from the Critic while preserving:
- Original composition
- Subject matter
- Artistic intent
- Natural appearance

The Editor uses Gemini's image editing capabilities with a fallback to traditional PIL enhancements for reliability.

### 3. The Generator

Creates permanent records:
- Saves original and edited images
- Generates side-by-side comparisons
- Creates metadata files
- Rebuilds the static website
- Updates the gallery view

### 4. The Publisher

GitHub Actions automation:
- Detects new photos in `inbox/`
- Runs the complete pipeline
- Commits processed results
- Deploys updated site to GitHub Pages

## Local Development

For testing locally before pushing:

```bash
# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Edit .env and add your GEMINI_API_KEY

# Run the pipeline manually
cd scripts
python pipeline.py
```

## Configuration

### Environment Variables

- `GEMINI_API_KEY`: Your Google Gemini API key (required)

### Supported Image Formats

- JPEG (.jpg, .jpeg)
- PNG (.png)

### Image Size Recommendations

- Minimum: 800x600 pixels
- Maximum: No hard limit (larger images take longer)
- Optimal: 1920x1080 to 4000x3000 pixels

## Architecture Philosophy

### No External State

REFRACT has zero external dependencies:
- No databases
- No external storage
- No third-party hosting

The repository itself IS the database. Every processed photo becomes a permanent, versioned record.

### File-Driven Design

Everything is triggered by file changes:
- New files in `inbox/` → Pipeline runs
- No manual intervention required
- Git history provides full audit trail

### Progressive Enhancement

The system is designed in layers:
- Core functionality works with minimal dependencies
- Fallback mechanisms ensure reliability
- Enhanced features activate when available

## Customization

### Modify the Critic

Edit `scripts/critic.py` to change analysis criteria or output format.

### Enhance the Editor

Edit `scripts/editor.py` to adjust how improvements are applied.

### Redesign the Site

Edit templates in `site/templates/`:
- `index.html` - Gallery page
- `entry.html` - Individual entry page
- `style.css` - Styling

### Adjust the Workflow

Edit `.github/workflows/refract-pipeline.yml` to change automation behavior.

## Troubleshooting

### Pipeline not running?

- Check GitHub Actions is enabled
- Verify `GEMINI_API_KEY` secret is set
- Ensure you pushed files to `inbox/`

### Images not processing?

- Check Actions tab for error logs
- Verify image format is supported
- Ensure API key has proper permissions

### Site not updating?

- Check GitHub Pages is enabled
- Verify Pages source is "GitHub Actions"
- Wait a few minutes for deployment

### API quota exceeded?

- Gemini has rate limits and quotas
- Spread out large batches of photos
- Check Google AI Studio for quota details

## Advanced Usage

### Batch Processing

Add multiple photos at once:

```bash
cp ~/Photos/batch/*.jpg inbox/
git add inbox/
git commit -m "Add photo batch"
git push
```

### Manual Pipeline Run

Trigger without new photos:
- Go to Actions tab
- Select "REFRACT Pipeline"
- Click "Run workflow"

### Custom Deployment

The static site in `site/public/` can be deployed anywhere:
- Netlify
- Vercel
- Any static hosting service

## API Reference

### Critic API

```python
from critic import PhotoCritic

critic = PhotoCritic(api_key)
result = critic.analyze(image_path)
# Returns: {score, improvements, notes}
```

### Editor API

```python
from editor import PhotoEditor

editor = PhotoEditor(api_key)
success = editor.edit(image_path, improvements, output_path)
# Returns: True/False
```

### Generator API

```python
from generator import SiteGenerator

generator = SiteGenerator(repo_root)
entry_dir = generator.create_entry(original, edited, metadata)
generator.build_site()
```

## Performance

- **Analysis**: ~2-5 seconds per photo
- **Editing**: ~5-10 seconds per photo
- **Site Build**: ~1 second per entry
- **Total**: ~10-20 seconds per photo

Large images and complex edits may take longer.

## Privacy & Security

- Photos are stored in your GitHub repository
- Public repos = public photos
- Use private repos for sensitive content
- API keys are stored as GitHub Secrets (encrypted)
- No data is sent to third parties except Google Gemini API

## Limitations

- Requires internet connection
- Subject to Gemini API rate limits
- Image quality depends on API capabilities
- Processing time scales with image size

## Future Enhancements

Potential improvements:
- Interactive before/after slider
- Multiple AI model support
- Custom editing presets
- Batch operation controls
- Advanced filtering and search
- Export to other platforms

## Contributing

This is a complete, working system. Feel free to:
- Fork and customize
- Submit improvements
- Share your results
- Report issues

## License

See LICENSE file for details.

## Credits

- Built with [Google Gemini AI](https://ai.google.dev/)
- Powered by [GitHub Actions](https://github.com/features/actions)
- Hosted on [GitHub Pages](https://pages.github.com/)

---

**REFRACT** - Transform your photography, automatically.
