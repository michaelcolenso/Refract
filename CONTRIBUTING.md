# Contributing to REFRACT

Thank you for your interest in improving REFRACT!

## Ways to Contribute

### 1. Report Issues
- Bugs you encounter
- Ideas for improvements
- Documentation clarifications

### 2. Improve Documentation
- Fix typos or unclear explanations
- Add examples
- Translate to other languages

### 3. Enhance Features
- Better AI prompts
- Improved image processing
- New site designs
- Performance optimizations

### 4. Share Your Results
- Show off your REFRACT gallery
- Share interesting findings
- Contribute example photos (with permission)

## Development Setup

```bash
# Fork and clone
git clone https://github.com/YOUR-USERNAME/refract.git
cd refract

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Add your GEMINI_API_KEY to .env

# Make changes
# ...

# Test your changes
cd scripts
python pipeline.py
```

## Making Changes

### Code Style

- Follow PEP 8 for Python code
- Use descriptive variable names
- Add docstrings to functions
- Comment complex logic

### Testing

Before submitting:

1. Test locally with real images
2. Verify the site builds correctly
3. Check for any errors in output
4. Ensure documentation is updated

### Commit Messages

Use clear, descriptive commit messages:

```
Good:
✓ "Improve Critic prompt for better color analysis"
✓ "Add support for WebP images"
✓ "Fix: Handle images without EXIF data"

Less helpful:
✗ "update"
✗ "fix bug"
✗ "changes"
```

## Areas for Contribution

### High Impact
- [ ] Add interactive before/after slider
- [ ] Support for more image formats (WebP, HEIC)
- [ ] Batch processing optimizations
- [ ] Alternative AI model support
- [ ] Custom site themes

### Medium Impact
- [ ] Better error messages
- [ ] Progress indicators
- [ ] Image EXIF preservation
- [ ] Thumbnail generation
- [ ] RSS feed for new entries

### Good First Contributions
- [ ] Documentation improvements
- [ ] Example photos and galleries
- [ ] CSS/styling enhancements
- [ ] Additional template designs
- [ ] Testing infrastructure

## Project Structure

```
scripts/
  critic.py       - AI analysis logic
  editor.py       - Image enhancement
  generator.py    - Site building
  pipeline.py     - Orchestration

site/
  templates/      - HTML/CSS templates
  public/         - Generated output

.github/
  workflows/      - CI/CD automation
```

## Guidelines

### Code Changes

1. Keep changes focused and atomic
2. Maintain backward compatibility
3. Don't add unnecessary dependencies
4. Preserve the zero-config philosophy

### AI Prompts

When modifying prompts:
- Test with diverse images
- Ensure JSON output remains strict
- Verify improvements are actionable
- Consider edge cases

### Site Design

For template changes:
- Keep responsive design
- Maintain accessibility
- Test on mobile devices
- Don't require JavaScript for core features

## Questions?

- Read the [Architecture](ARCHITECTURE.md) for technical details
- Check [Testing](TESTING.md) for testing guidance
- Review [README](README.md) for usage info

## License

By contributing, you agree your contributions will be licensed under the same license as the project.

---

**Thank you for making REFRACT better!** 🎨
