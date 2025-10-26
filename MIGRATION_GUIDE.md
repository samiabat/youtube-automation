# Migration Guide - Old vs New Implementation

## Overview

This guide helps you understand the changes between the old monolithic script (`auto_video_backaup.py`) and the new modular implementation.

## What Changed?

### Before (auto_video_backaup.py)
- Single 555-line script with everything mixed together
- API keys hardcoded or from environment variables directly
- Simple keyword extraction (4 keywords max)
- Limited fallback - black screens when no video found
- No structured logging
- No image fallback support

### After (Modular Implementation)
- **config.py** - Centralized configuration with .env support
- **transcribe.py** - Audio transcription and caption parsing
- **download_assets.py** - Stock provider integration with image fallback
- **video_builder.py** - Video assembly and rendering
- **main.py** - Clean CLI interface

## Key Improvements

### 1. No More Black Screens ✓

**Old behavior:**
```python
if not url:
    # Creates black screen with query text
    bg = ColorClip(size=(w, h), color=(0, 0, 0)).set_duration(seg.dur)
```

**New behavior:**
```python
# Try video → image → simplified query → theme fallback
url, asset_type = fetch_asset_url(query, primary, fallback, image_fallback)
if not url:
    simplified_query = simplify_query(query, style)
    url, asset_type = fetch_asset_url(simplified_query, primary, fallback, image_fallback)
```

### 2. Better Content Relevance ✓

**Old approach:**
```python
def smart_query_for_segment(seg: Segment, style: str) -> str:
    kws = extract_keywords(seg.text, topk=4)  # Just 4 keywords
    if not kws:
        return random.choice(THEME_MAP.get(style, THEME_MAP["general"]))
    q = " ".join(kws)
```

**New approach:**
```python
def generate_query_for_segment(seg: Segment, style: str, use_full_text: bool = True) -> str:
    if use_full_text and len(text) > 0:
        # Use full text for better context
        query = text[:100]
        return query
    # Falls back to keywords only if needed
```

### 3. Configuration Management ✓

**Old way:**
```python
# Keys directly from environment
provider_key = os.getenv("SOME_API_KEY")
```

**New way:**
```python
# Centralized in config.py
class Config:
    WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "small")
    DEFAULT_RESOLUTION: str = os.getenv("DEFAULT_RESOLUTION", "1920x1080")
```

### 4. Comprehensive Logging ✓

**Old way:**
```python
# No logging for asset selection
print(f"[Whisper] Generating captions...")
```

**New way:**
```python
logger.info(f"--- Processing segment {seg.idx} ({seg.start:.2f}s - {seg.end:.2f}s) ---")
logger.info(f"Text: '{seg.text}'")
logger.info(f"Generated query: '{query}'")
logger.info(f"Creating clip for segment {seg.idx}")
```

### 5. Fallback Support ✓

**New feature - gradient backgrounds when needed:**
```python
def create_fallback_clip(w, h, duration, query):
    """Creates gradient background with text overlay"""
```

## Migration Path

### If you were using the old script:

**Old command:**
```bash
python auto_video_backaup.py \
  --audio narration.mp3 \
  --autocaptions \
  --out video.mp4 \
  --style general
```

**New command:**
```bash
# First time: setup .env file (optional)
cp .env.example .env
# Edit .env to customize settings

# Then run with new script
python main.py \
  --audio narration.mp3 \
  --autocaptions \
  --out video.mp4
```

### Environment Variables

**New (.env file):**
```env
WHISPER_MODEL=small
DEFAULT_RESOLUTION=1920x1080
DEFAULT_FPS=30
LOG_LEVEL=INFO
```

## Backward Compatibility

The old script (`auto_video_backaup.py`) is still available as a backup. It will continue to work with the original approach.

To use the old script:
```bash
python auto_video_backaup.py --audio narration.mp3 --autocaptions --out video.mp4
```

## Feature Comparison Table

| Feature | Old Script | New Implementation |
|---------|-----------|-------------------|
| API Key Management | ENV vars | .env file + config |
| Query Generation | Keywords only | Full text + fallbacks |
| Video Fallback | Black screen | Video → Image → Simplified |
| Logging | Basic prints | Structured logging |
| Code Organization | Single file | Modular (5 files) |
| Image Support | No | Yes |
| Configuration | Command line | .env + CLI |
| Error Messages | Limited | Detailed with context |
| Custom Queries | JSON file | JSON file (same) |

## Benefits of New Implementation

1. **Easier to maintain** - Each module has a single responsibility
2. **Better debugging** - Comprehensive logs show exactly what's happening
3. **More reliable** - Multiple fallback strategies prevent blank videos
4. **More relevant** - Full-text queries find better matching footage
5. **More secure** - API keys in .env file, not in code or shell history
6. **Easier to extend** - Add new providers or features in isolated modules

## Testing the New Implementation

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Setup configuration:**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

3. **Run a test:**
   ```bash
   python main.py --audio narration.mp3 --autocaptions --out test.mp4 --log-level DEBUG
   ```

4. **Check the logs:**
   ```bash
   cat automation.log
   ```

## Need Help?

- Check `USAGE_GUIDE.md` for detailed usage examples
- See `README.md` for quick start guide
- Review `automation.log` for debugging
- Old script is still available at `auto_video_backaup.py`
