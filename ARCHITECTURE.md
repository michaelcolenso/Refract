# REFRACT Architecture

Detailed technical architecture and design decisions.

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                         USER                                 │
│                           ↓                                  │
│                 Add photos to inbox/                         │
│                           ↓                                  │
│                     git push                                 │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ↓
┌─────────────────────────────────────────────────────────────┐
│                   GITHUB ACTIONS                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Trigger: Push to main with changes in inbox/       │   │
│  └──────────────────────────────────────────────────────┘   │
│                         ↓                                    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  1. Check for new images                            │   │
│  │  2. Setup Python environment                        │   │
│  │  3. Install dependencies                            │   │
│  └──────────────────────────────────────────────────────┘   │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ↓
┌─────────────────────────────────────────────────────────────┐
│                   PIPELINE ORCHESTRATOR                      │
│                   (scripts/pipeline.py)                      │
│                                                              │
│  FOR EACH IMAGE IN INBOX:                                   │
│    ├─→ CRITIC  → analyze()  → {score, improvements, notes} │
│    ├─→ EDITOR  → edit()     → edited_image                 │
│    ├─→ GENERATOR → create_entry() → permanent record       │
│    └─→ CLEANUP → archive original from inbox                │
│                                                              │
│  AFTER ALL IMAGES:                                          │
│    └─→ GENERATOR → build_site() → static website           │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ↓
┌─────────────────────────────────────────────────────────────┐
│                      STORAGE                                 │
│                                                              │
│  processed/                                                  │
│    └── YYYYMMDD-HHMMSS-xxxx/                               │
│        ├── original.jpg                                     │
│        ├── edited.jpg                                       │
│        └── metadata.json                                    │
│                                                              │
│  site/public/                                               │
│    ├── index.html                                           │
│    ├── {entry-id}.html                                      │
│    ├── style.css                                            │
│    └── images/                                              │
│        ├── {id}-original.jpg                                │
│        ├── {id}-edited.jpg                                  │
│        └── {id}-comparison.jpg                              │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ↓
┌─────────────────────────────────────────────────────────────┐
│                   GITHUB ACTIONS                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  1. Commit processed/ and site/public/              │   │
│  │  2. Push to repository                              │   │
│  │  3. Deploy site to GitHub Pages                     │   │
│  └──────────────────────────────────────────────────────┘   │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ↓
┌─────────────────────────────────────────────────────────────┐
│                    GITHUB PAGES                              │
│                  (Static Website)                            │
│                                                              │
│  Gallery view with all entries                              │
│  Individual entry pages with comparisons                    │
│  Responsive, accessible design                              │
└─────────────────────────────────────────────────────────────┘
```

## Component Architecture

### 1. The Critic (scripts/critic.py)

**Purpose:** Analyze photographs using Gemini Vision

**Input:**
- Image file path (JPEG/PNG)

**Process:**
1. Load image using PIL
2. Craft analysis prompt
3. Call Gemini Vision API (`gemini-2.0-flash-exp`)
4. Parse and validate JSON response
5. Ensure strict schema compliance

**Output:**
```json
{
  "score": 0-100,
  "improvements": ["action 1", "action 2", ...],
  "notes": "brief explanation"
}
```

**Key Features:**
- Strict JSON output enforcement
- Robust error handling
- Markdown cleanup
- Schema validation

**API Integration:**
```python
genai.configure(api_key=api_key)
model = genai.GenerativeModel('gemini-2.0-flash-exp')
response = model.generate_content([prompt, image])
```

### 2. The Editor (scripts/editor.py)

**Purpose:** Apply improvements to photographs

**Input:**
- Original image path
- List of improvements
- Output path

**Process:**
1. Load original image
2. Construct editing prompt with improvements
3. Call Gemini API for image editing
4. Extract generated image data
5. Fallback to PIL enhancements if needed

**Output:**
- Enhanced image file

**Fallback Strategy:**
The Editor implements a two-tier approach:
1. **Primary:** Gemini image generation with edit instructions
2. **Fallback:** PIL-based enhancements (brightness, contrast, color, sharpness)

This ensures reliability even if the API response format changes.

**PIL Fallback Intelligence:**
```python
# Analyzes improvement text to determine adjustments
if 'brightness' in improvements:
    apply brightness enhancement
if 'contrast' in improvements:
    apply contrast enhancement
if 'saturation' in improvements:
    apply color enhancement
```

### 3. The Generator (scripts/generator.py)

**Purpose:** Create permanent records and build static site

**Responsibilities:**

#### A. Entry Creation
```python
create_entry(original, edited, metadata) → entry_directory
```

1. Generate unique ID: `timestamp-random_hex`
2. Create directory in `processed/`
3. Copy original and edited images
4. Save metadata.json
5. Return entry path

#### B. Comparison Images
```python
create_comparison_image(original, edited, output)
```

1. Load both images
2. Resize to consistent height (800px)
3. Create side-by-side composition
4. Save as high-quality JPEG

#### C. Site Building
```python
build_site()
```

1. Load all entries from `processed/`
2. Copy images to `site/public/images/`
3. Generate comparison images
4. Render index.html (gallery view)
5. Render individual entry pages
6. Copy CSS and assets

**Template Engine:** Jinja2

**Output Structure:**
```
site/public/
├── index.html          # Gallery page
├── {entry-id}.html     # Individual entries
├── style.css           # Styling
└── images/
    └── {id}-*.(jpg)    # All images
```

### 4. The Pipeline Orchestrator (scripts/pipeline.py)

**Purpose:** Coordinate the complete workflow

**Process:**
```python
1. Initialize components (Critic, Editor, Generator)
2. Scan inbox/ for new images
3. FOR EACH image:
     a. Analyze with Critic
     b. Edit with Editor
     c. Create entry with Generator
     d. Archive original from inbox
4. Rebuild entire site
5. Report summary
```

**Error Handling:**
- Continues processing other images if one fails
- Detailed logging for debugging
- Graceful degradation

**State Management:**
- No persistent state
- Each run is idempotent
- Can be re-run safely

## Data Flow

### Image Processing Flow

```
Original Image (inbox/)
    ↓
[Critic Analysis]
    ↓
Critique JSON {score, improvements, notes}
    ↓
[Editor Enhancement]
    ↓
Edited Image (temp)
    ↓
[Generator Record]
    ↓
Permanent Entry (processed/{id}/)
    ├── original.jpg
    ├── edited.jpg
    └── metadata.json
    ↓
[Generator Site Build]
    ↓
Static Site (site/public/)
    ├── Gallery entry card
    └── Individual entry page
```

### Site Generation Flow

```
All Entries in processed/
    ↓
[Load Metadata]
    ↓
Entry Objects List
    ↓
[Copy Images to public/]
    ↓
[Generate Comparisons]
    ↓
[Render Templates]
    ├── index.html (with all entries)
    └── {id}.html (for each entry)
    ↓
[Copy Static Assets]
    ↓
Complete Static Site
```

## Automation Architecture

### GitHub Actions Workflow

**File:** `.github/workflows/refract-pipeline.yml`

**Jobs:**

#### 1. process-photos
```yaml
Trigger: push to main (inbox/** changes)
Steps:
  1. Checkout repo
  2. Setup Python 3.11
  3. Install dependencies
  4. Check for images
  5. Run pipeline
  6. Commit results
  7. Push to repo
```

#### 2. deploy-site
```yaml
Depends: process-photos
Steps:
  1. Checkout repo
  2. Setup Pages
  3. Upload site artifact
  4. Deploy to Pages
```

**Permissions:**
- `contents: write` - Commit processed results
- `pages: write` - Deploy to GitHub Pages
- `id-token: write` - GitHub Pages authentication

### Trigger Conditions

The workflow runs when:
1. New files added to `inbox/`
2. Changes to `scripts/`
3. Changes to workflow file
4. Manual trigger via Actions UI

## Design Principles

### 1. No External State

**Decision:** Repository is the database

**Rationale:**
- Simplicity: No external services to manage
- Portability: Clone and go
- Versioning: Git tracks all changes
- Durability: GitHub's reliability

**Implementation:**
- All data stored as files
- All state derived from file system
- No configuration databases
- No user sessions

### 2. File-Driven Design

**Decision:** Everything triggered by file changes

**Rationale:**
- Intuitive: Drop files to process
- Git-native: Standard workflow
- Automatable: CI/CD integration
- Auditable: Git history

**Implementation:**
- Watch `inbox/` for new files
- Git triggers automation
- File removal signals completion
- Directory structure provides organization

### 3. Progressive Enhancement

**Decision:** Layered functionality with fallbacks

**Rationale:**
- Reliability: Keep working if API changes
- Flexibility: Adapt to constraints
- User experience: Always produce output

**Implementation:**
- Primary: Advanced AI features
- Fallback: Traditional algorithms
- Graceful degradation at each layer

### 4. Separation of Concerns

**Decision:** Modular components with single responsibilities

**Rationale:**
- Maintainability: Easy to update
- Testability: Isolate functionality
- Extensibility: Add features easily
- Clarity: Clear boundaries

**Implementation:**
```
Critic    → Analysis only
Editor    → Editing only
Generator → Documentation only
Pipeline  → Orchestration only
```

### 5. Zero-Touch Operation

**Decision:** Fully automated pipeline

**Rationale:**
- User experience: Drop and forget
- Consistency: Same process every time
- Scalability: Handle any volume
- Efficiency: No manual steps

**Implementation:**
- GitHub Actions automation
- Automatic commits and deployment
- Self-documenting entries
- No configuration required

## Technology Choices

### Python
**Why:**
- Excellent AI/ML libraries
- PIL for image processing
- Simple scripting
- Great API support

### Google Gemini
**Why:**
- State-of-the-art vision
- Image editing capabilities
- Reasonable pricing
- Good documentation

### GitHub Actions
**Why:**
- Free for public repos
- Integrated with GitHub
- Powerful automation
- Easy to configure

### GitHub Pages
**Why:**
- Free static hosting
- Automatic deployment
- Custom domains
- HTTPS by default

### Jinja2
**Why:**
- Powerful templating
- Python integration
- Clear syntax
- Good performance

## Scalability Considerations

### Image Volume

**Current:** Optimized for personal use (10-100 photos)

**Scaling options:**
- Batch processing: Process in parallel
- Incremental builds: Only update changed entries
- CDN: Use external image hosting
- Pagination: Divide gallery into pages

### Repository Size

**Concern:** Git repositories grow with binary files

**Mitigation:**
- Git LFS for large images
- Periodic archival of old entries
- External storage option
- Compression optimization

### API Costs

**Concern:** Gemini API has usage limits

**Mitigation:**
- Rate limiting in pipeline
- Batch processing controls
- Cost monitoring
- Fallback to free tier

## Security Considerations

### API Key Management

**Security:**
- Stored as GitHub Secret (encrypted)
- Never committed to repo
- Access controlled by GitHub permissions
- Rotatable without code changes

### Repository Privacy

**Public repos:** Anyone can see photos
**Private repos:** Access controlled

**Recommendation:** Use private repos for personal photos

### Dependency Security

**Practices:**
- Pin dependency versions
- Regular updates
- Vulnerability scanning
- Minimal dependencies

## Future Architecture Enhancements

### Potential Improvements

1. **Plugin System**
   - Custom Critic algorithms
   - Alternative Editor backends
   - Custom site themes

2. **Multi-Model Support**
   - Compare different AI models
   - A/B testing
   - Ensemble approaches

3. **Advanced Caching**
   - Avoid reprocessing
   - Faster site builds
   - Smart invalidation

4. **Real-time Processing**
   - Webhook triggers
   - Streaming updates
   - Live preview

5. **Enhanced Analytics**
   - Quality trends
   - Improvement effectiveness
   - Usage statistics

## Conclusion

REFRACT's architecture balances:
- **Simplicity** - Easy to understand and use
- **Power** - Advanced AI capabilities
- **Reliability** - Fallbacks and error handling
- **Automation** - Zero-touch operation
- **Portability** - No external dependencies

The result is a robust, self-contained photography improvement system that just works.
