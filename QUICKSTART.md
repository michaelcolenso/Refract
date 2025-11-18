# REFRACT Quick Start

Get up and running in 5 minutes.

## Setup (One-Time)

### 1. Get API Key
- Visit: https://makersuite.google.com/app/apikey
- Create API key
- Copy it

### 2. Add to GitHub
- Go to: **Settings → Secrets and variables → Actions**
- New secret: `GEMINI_API_KEY`
- Paste your key
- Save

### 3. Enable Pages
- Go to: **Settings → Pages**
- Source: **GitHub Actions**
- Save

## Usage (Every Time)

```bash
# 1. Add photos
cp ~/Photos/my-photo.jpg inbox/

# 2. Push
git add inbox/
git commit -m "Add photos"
git push

# 3. Wait ~1-2 minutes

# 4. Visit your site!
```

## Your Site URL

```
https://YOUR-USERNAME.github.io/YOUR-REPO-NAME/
```

## Check Progress

- **Actions Tab**: See pipeline running
- **processed/**: See completed entries
- **Site URL**: See final gallery

## That's It!

Drop photos → Push → Enjoy

---

For detailed docs, see [README.md](README.md)
