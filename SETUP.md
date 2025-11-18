# REFRACT Setup Guide

Complete step-by-step instructions to get REFRACT running.

## Prerequisites Checklist

- [ ] GitHub account
- [ ] Google Gemini API key
- [ ] This repository cloned or forked
- [ ] Photos to process

## Step 1: Get Your Gemini API Key

1. Visit [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Sign in with your Google account
3. Click "Create API Key"
4. Copy the key (you'll need it in the next step)

**Important:** Keep your API key secure. Never commit it to the repository.

## Step 2: Configure GitHub Secrets

1. Go to your repository on GitHub
2. Click **Settings** (top menu)
3. In the left sidebar, expand **Secrets and variables**
4. Click **Actions**
5. Click **New repository secret**
6. Add the secret:
   - Name: `GEMINI_API_KEY`
   - Value: (paste your API key)
7. Click **Add secret**

## Step 3: Enable GitHub Pages

1. Still in **Settings**, scroll to **Pages** (left sidebar)
2. Under **Source**, select:
   - Source: **GitHub Actions**
3. Click **Save**

That's it! GitHub Pages is now enabled.

## Step 4: Test the System

### Option A: Add a Test Photo

1. Find a photo on your computer
2. Copy it to the `inbox/` folder in this repository
3. Commit and push:

```bash
# Add the photo
cp ~/Pictures/my-test-photo.jpg inbox/

# Commit
git add inbox/
git commit -m "Add test photo"

# Push to trigger the pipeline
git push
```

### Option B: Manual Trigger

1. Go to the **Actions** tab in GitHub
2. Click on **REFRACT Pipeline** in the left sidebar
3. Click **Run workflow**
4. Click the green **Run workflow** button

## Step 5: Watch the Pipeline Run

1. Go to the **Actions** tab
2. You'll see your workflow running
3. Click on the workflow to see detailed logs
4. Wait for it to complete (usually 1-2 minutes)

### What Happens

The pipeline will:
1. ✓ Check out your repository
2. ✓ Install Python dependencies
3. ✓ Check for new images
4. ✓ Run the Critic (analyze photos)
5. ✓ Run the Editor (enhance photos)
6. ✓ Run the Generator (create site)
7. ✓ Commit results back to repo
8. ✓ Deploy to GitHub Pages

## Step 6: View Your Results

### Check the Processed Entry

1. In your repository, navigate to `processed/`
2. You'll see a new folder: `YYYYMMDD-HHMMSS-xxxx/`
3. Inside you'll find:
   - `original.jpg` - Your original photo
   - `edited.jpg` - The AI-enhanced version
   - `metadata.json` - The analysis

### Visit Your Site

1. Go to **Settings → Pages**
2. Under "Your site is live at", click the URL
3. You'll see your REFRACT gallery!

The URL format is usually:
```
https://YOUR-USERNAME.github.io/YOUR-REPO-NAME/
```

## Local Development Setup (Optional)

If you want to test locally before pushing:

### 1. Clone the repository

```bash
git clone https://github.com/YOUR-USERNAME/YOUR-REPO-NAME.git
cd YOUR-REPO-NAME
```

### 2. Install Python dependencies

```bash
# Optional: Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure environment

```bash
# Copy example environment file
cp .env.example .env

# Edit .env and add your API key
# GEMINI_API_KEY=your_actual_api_key_here
```

### 4. Add test photos

```bash
cp ~/Pictures/*.jpg inbox/
```

### 5. Run the pipeline

```bash
cd scripts
python pipeline.py
```

### 6. View results locally

Open `site/public/index.html` in your browser.

## Usage Workflow

Once set up, using REFRACT is simple:

```bash
# 1. Add photos
cp ~/Photos/*.jpg inbox/

# 2. Commit and push
git add inbox/
git commit -m "Add new photos"
git push

# 3. Wait for automation (1-2 minutes)

# 4. Visit your site
```

That's it! The pipeline handles everything else automatically.

## Verification Checklist

After setup, verify everything works:

- [ ] API key is set in GitHub Secrets
- [ ] GitHub Pages is enabled
- [ ] GitHub Actions can run workflows
- [ ] Test photo processes successfully
- [ ] Processed entry appears in `processed/`
- [ ] Site deploys to GitHub Pages
- [ ] Gallery shows the new entry

## Troubleshooting

### "GEMINI_API_KEY environment variable not set"

- Check the secret name is exactly `GEMINI_API_KEY`
- Verify you added it to Secrets (not Variables)
- Try re-running the workflow

### "No new images found in inbox/"

- Make sure you added images to `inbox/` folder
- Check file extensions are .jpg, .jpeg, or .png
- Verify you committed and pushed the files

### Workflow doesn't run

- Check Actions is enabled: Settings → Actions → General
- Verify workflow file is in `.github/workflows/`
- Try manual trigger from Actions tab

### Site doesn't deploy

- Verify Pages source is "GitHub Actions"
- Check workflow completed successfully
- Wait a few minutes for deployment
- Try force refresh (Ctrl+F5)

### API errors

- Check your API key is valid
- Verify you have API quota remaining
- Check [Google AI Studio](https://makersuite.google.com/) for limits

## Getting Help

- Check the [README.md](README.md) for detailed documentation
- Review workflow logs in the Actions tab
- Check GitHub Pages deployment status
- Verify all files are in the correct locations

## Next Steps

Once everything is working:

1. **Process your photos**: Add your actual photography to `inbox/`
2. **Customize the site**: Edit templates in `site/templates/`
3. **Adjust the analysis**: Modify `scripts/critic.py`
4. **Enhance the editing**: Customize `scripts/editor.py`
5. **Share your gallery**: Send people your GitHub Pages URL

---

**You're all set!** Start dropping photos into `inbox/` and watch REFRACT transform them automatically.
