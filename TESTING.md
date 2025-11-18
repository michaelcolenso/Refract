# REFRACT Testing Guide

How to test the system locally and verify it works.

## Local Testing

### Prerequisites

```bash
# Install Python dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Edit .env and add: GEMINI_API_KEY=your_key_here
```

### Test Individual Components

#### 1. Test the Critic

```bash
# Download a test image (or use your own)
curl -o test.jpg https://picsum.photos/1200/800

# Run critic
cd scripts
python critic.py ../test.jpg
```

**Expected output:**
```json
{
  "score": 75,
  "improvements": [
    "Increase brightness by 15%",
    "Boost color saturation",
    "..."
  ],
  "notes": "..."
}
```

#### 2. Test the Editor

```bash
# Use output from critic test
python editor.py ../test.jpg '["Increase brightness", "Boost saturation"]' ../test-edited.jpg
```

**Expected output:**
```
Image successfully edited: ../test-edited.jpg
```

#### 3. Test the Generator

```bash
# Create a test entry
python generator.py create ../test.jpg ../test-edited.jpg '{"score": 85, "improvements": ["test"], "notes": "test"}'

# Build the site
python generator.py build
```

**Expected output:**
```
Entry created: YYYYMMDD-HHMMSS-xxxx
Site built successfully: 1 entries
```

#### 4. Test the Full Pipeline

```bash
# Add a test image to inbox
cp ../test.jpg ../inbox/

# Run full pipeline
python pipeline.py
```

**Expected output:**
```
REFRACT - Automated Photography Improvement Pipeline
====================================
Found 1 image(s) to process:
  - test.jpg

Processing: test.jpg
====================================

STEP 1: Analyzing photograph...
  Score: 85/100
  ...

STEP 2: Applying improvements...
  ...

STEP 3: Creating documentation...
  ...

STEP 4: Archiving original...
  ...

Rebuilding static site...
  ...

Pipeline Summary
====================================
  Processed: 1 successful, 0 failed
  Total entries: 1
```

### View Results Locally

```bash
# Open the site in browser
# From repo root:
open site/public/index.html
# Or on Linux:
xdg-open site/public/index.html
# Or on Windows:
start site/public/index.html
```

## GitHub Actions Testing

### Test Without Photos

```bash
# Trigger workflow manually
# Go to Actions tab → REFRACT Pipeline → Run workflow
```

This should:
- ✓ Run successfully
- ✓ Report "No new images found"
- ✓ Deploy existing site

### Test With Photos

```bash
# Add test image
cp ~/Pictures/test.jpg inbox/

# Commit and push
git add inbox/
git commit -m "Test: Add photo"
git push

# Watch in Actions tab
```

This should:
- ✓ Detect the image
- ✓ Process it
- ✓ Commit results
- ✓ Deploy updated site

### Verify Results

1. **Check processed/ directory**
   - New folder created: `YYYYMMDD-HHMMSS-xxxx/`
   - Contains: original.jpg, edited.jpg, metadata.json

2. **Check site/public/ directory**
   - Updated index.html
   - New entry page: `{entry-id}.html`
   - Images in images/

3. **Check GitHub Pages**
   - Visit your Pages URL
   - See the new entry in gallery
   - Click to view details

## Troubleshooting Tests

### Critic fails with API error

**Problem:** Invalid API key or quota exceeded

**Solution:**
```bash
# Verify API key is set
echo $GEMINI_API_KEY

# Check it's not empty/invalid
# Get new key from: https://makersuite.google.com/app/apikey
```

### Editor produces identical image

**Problem:** Fallback to basic PIL edits

**Solution:**
- This is expected behavior
- The fallback ensures reliability
- Check improvements are being applied

### Generator fails to build site

**Problem:** Missing template or dependencies

**Solution:**
```bash
# Verify templates exist
ls site/templates/

# Should see:
# - index.html
# - entry.html
# - style.css

# Reinstall if needed
pip install -r requirements.txt --force-reinstall
```

### Pipeline skips images

**Problem:** Already processed or wrong format

**Solution:**
```bash
# Check inbox
ls -la inbox/

# Verify file extensions: .jpg, .jpeg, .png
# Make sure not .gitkeep or hidden files

# Clear and retry
rm -rf processed/*  # WARNING: Deletes all entries
```

## Testing Checklist

Before deploying to production:

- [ ] API key works locally
- [ ] Critic analyzes images correctly
- [ ] Editor produces modified images
- [ ] Generator creates entries
- [ ] Pipeline processes end-to-end
- [ ] Site builds and displays correctly
- [ ] GitHub Actions workflow runs
- [ ] Results commit back to repo
- [ ] GitHub Pages deploys successfully
- [ ] Images display on live site

## Performance Testing

### Single Image

```bash
time python scripts/pipeline.py
```

**Expected:** 10-30 seconds total

### Multiple Images

```bash
# Add 5 test images
for i in {1..5}; do
  cp test.jpg inbox/test-$i.jpg
done

time python scripts/pipeline.py
```

**Expected:** ~1-2 minutes for 5 images

### Large Image

```bash
# Test with 4000x3000 image
# Should still work, just slower
```

**Expected:** 30-60 seconds per large image

## Error Testing

### Missing API Key

```bash
unset GEMINI_API_KEY
python scripts/pipeline.py
```

**Expected:** Clear error message

### Invalid Image

```bash
# Create invalid file
echo "not an image" > inbox/fake.jpg
python scripts/pipeline.py
```

**Expected:** Error logged, continues with other images

### Network Issues

```bash
# Disconnect network
# Run pipeline
```

**Expected:** API errors, falls back gracefully

## Validation Tests

### Check JSON Schema

```bash
# Run critic and validate output
python scripts/critic.py test.jpg | jq .

# Should parse without errors
# Should have: score, improvements, notes
```

### Check Image Output

```bash
# Verify edited image exists and is valid
python scripts/editor.py test.jpg '["test"]' output.jpg
file output.jpg
# Should say: JPEG image data

# Verify it opens
open output.jpg  # or xdg-open/start
```

### Check Site Structure

```bash
# After building
cd site/public

# Verify structure
ls
# Should see: index.html, style.css, images/

ls images/
# Should see: *-original.jpg, *-edited.jpg, *-comparison.jpg

# Validate HTML
# curl https://validator.w3.org/...
```

## Continuous Testing

### Set Up Test Automation

Create `.github/workflows/test.yml`:

```yaml
name: Test REFRACT

on: [pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: python -m pytest tests/  # If you add tests
```

### Add Unit Tests

Create `tests/test_critic.py`:

```python
import unittest
from scripts.critic import PhotoCritic

class TestCritic(unittest.TestCase):
    def test_analyze_format(self):
        # Test that output has correct schema
        pass
```

## Success Criteria

The system is working correctly when:

1. ✓ New images in inbox/ are processed automatically
2. ✓ Critic produces valid JSON with score and improvements
3. ✓ Editor creates modified images
4. ✓ Generator creates permanent records
5. ✓ Site builds and displays all entries
6. ✓ GitHub Actions runs without errors
7. ✓ Changes commit back to repository
8. ✓ Live site updates with new entries

---

**Happy Testing!** 🧪

For issues, check logs in Actions tab or run locally with verbose output.
