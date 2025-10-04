# YouTube Automation - Usage Guide

## Installation Steps

1. **Clone the repository**
   ```bash
   git clone https://github.com/samiabat/youtube-automation.git
   cd youtube-automation
   ```

2. **Install Python dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Download NLTK data**
   ```bash
   python -c "import nltk; nltk.download('punkt'); nltk.download('punkt_tab'); nltk.download('stopwords')"
   ```

4. **Setup API keys**
   ```bash
   cp .env.example .env
   # Edit .env and add your API keys
   ```

## Basic Workflow

### 1. Prepare Your Audio

Create or obtain an audio narration file (MP3 or WAV format). This will be the voiceover for your video.

Example: `narration.mp3`

### 2. Generate Video (Simple)

```bash
python main.py --audio narration.mp3 --autocaptions --out video.mp4
```

This will:
- Transcribe your audio using Whisper
- Generate captions
- Find relevant stock footage
- Create a video with subtitles

### 3. Generate Video (With Existing Captions)

If you already have captions:

```bash
python main.py --audio narration.mp3 --captions my_captions.vtt --out video.mp4
```

## Advanced Usage

### Vertical Video (For Mobile/TikTok/Instagram)

```bash
python main.py \
  --audio narration.mp3 \
  --autocaptions \
  --resolution 1080x1920 \
  --out vertical_video.mp4
```

### Different Video Styles

Choose a style that influences stock footage selection:

```bash
# Cinematic style
python main.py --audio narration.mp3 --autocaptions --style cinematic --out video.mp4

# Nature documentary style
python main.py --audio narration.mp3 --autocaptions --style nature --out video.mp4

# Technology/coding style
python main.py --audio narration.mp3 --autocaptions --style tech --out video.mp4
```

### Using Title for Better Query Relevance

Provide your video's title to ensure stock footage stays relevant to the main topic:

```bash
python main.py \
  --audio narration.mp3 \
  --autocaptions \
  --title "Understanding the Solar System" \
  --style nature \
  --out solar_system.mp4
```

**Why use --title?**

When your narration mentions something in passing that's not central to your topic, the title helps keep queries on track. For example:

- **Without --title:** Segment says "if we compare this to a football field" → searches for football-related content
- **With --title "Understanding the Solar System":** Same segment → searches for "solar system football field" → returns space-related content showing scale

The title keywords are intelligently combined with each segment's content to maintain topical relevance.

### Custom Search Queries

Create a `queries.json` file to control exactly what footage appears for each segment:

```json
{
  "0": "golden hour mountain landscape",
  "1": "busy city street timelapse",
  "2": "person working on laptop in cafe",
  "3": "sunset over ocean waves"
}
```

Then use it:

```bash
python main.py \
  --audio narration.mp3 \
  --captions captions.vtt \
  --custom-queries queries.json \
  --out video.mp4
```

### Higher Quality / Different Frame Rate

```bash
python main.py \
  --audio narration.mp3 \
  --autocaptions \
  --resolution 3840x2160 \
  --fps 60 \
  --out high_quality.mp4
```

### Without Subtitles

```bash
python main.py \
  --audio narration.mp3 \
  --autocaptions \
  --no-subs \
  --out no_subs_video.mp4
```

### With Transitions

Add smooth crossfade transitions between clips:

```bash
python main.py \
  --audio narration.mp3 \
  --autocaptions \
  --transitions \
  --out smooth_video.mp4
```

### With Background Music

Add classical/ambient background music to enhance storytelling (enabled by default):

```bash
# With custom volume (15% instead of default 10%)
python main.py \
  --audio narration.mp3 \
  --autocaptions \
  --music-volume 0.15 \
  --out video_with_music.mp4

# Disable background music
python main.py \
  --audio narration.mp3 \
  --autocaptions \
  --no-background-music \
  --out video_no_music.mp4
```

**Background Music Features:**
- Automatically downloads royalty-free classical/ambient music
- Loops music to match video duration
- Mixed at low volume (default 10%) to not overpower narration
- Gracefully continues without music if download fails

## Clip Variation and Quality

The system now includes enhanced clip variation to reduce repetitive footage:

### How It Works

1. **Multi-Provider Search**: Queries both Pexels and Pixabay simultaneously
2. **More Results**: Fetches up to 10 clips per query (instead of 3)
3. **Random Selection**: Randomly picks from available clips instead of always using the first one
4. **URL Tracking**: Remembers used clips to avoid immediate repetition
5. **Smart Reuse**: If all clips have been used, it still varies the order

### Result

Much more diverse and engaging videos with minimal clip repetition!

## Troubleshooting Common Issues

### Issue: "No API keys found"

**Solution:** Make sure you have created `.env` file and added at least one API key:
```bash
cp .env.example .env
# Edit .env and add your keys
```

### Issue: "NLTK data not found"

**Solution:** Download NLTK data:
```bash
python -c "import nltk; nltk.download('punkt'); nltk.download('stopwords')"
```

### Issue: "ffmpeg not found"

**Solution:** Install ffmpeg:
- **Ubuntu/Debian:** `sudo apt-get install ffmpeg`
- **macOS:** `brew install ffmpeg`
- **Windows:** Download from https://ffmpeg.org/

### Issue: Video has black screens

This should be fixed in the new version! The script now:
1. First tries to find video clips
2. Falls back to images if no videos found
3. Uses simplified queries if needed
4. Shows error text on black background as last resort

Check the `automation.log` file to see what's happening with each segment.

### Issue: Stock footage not relevant

Try these approaches:

1. **Use the --title parameter** to provide topic context:
   ```bash
   python main.py --audio narration.mp3 --autocaptions --title "Your Main Topic" --out video.mp4
   ```
   This helps ensure all queries stay relevant to your video's main subject.

2. **Use custom queries** for important segments (see Custom Search Queries above)

3. **Check the logs** in `automation.log` to see what queries are being generated

4. **Try a different style** that might match your content better:
   ```bash
   python main.py --audio narration.mp3 --autocaptions --style cinematic --out video.mp4
   ```

## Understanding the Logs

The script creates detailed logs in `automation.log`. Here's what to look for:

```
INFO - Searching Pexels for: 'Welcome to our tutorial'
INFO - Pexels returned 3 video URLs
INFO - Using video from primary provider
INFO - Using video asset for segment 0
```

This tells you:
- What query was used
- Which provider responded
- What type of asset was used (video/image)

If you see:
```
WARNING - No results for query '...', trying simplified query
```

This means the full-text query didn't find results, and it's trying keywords instead.

## Production Tips

1. **Test with short clips first** before processing long narrations

2. **Always use --title** to provide topic context and ensure relevant footage

3. **Use custom queries** for key segments where visual relevance is critical

4. **Review the log file** after generation to understand asset selection

5. **Keep audio files under 10 minutes** for faster processing

6. **Use appropriate styles**:
   - `general`: Safe choice for most content
   - `cinematic`: Polished, professional look
   - `nature`: Outdoor, natural environments
   - `tech`: Digital, technology-focused visuals

7. **Optimize for your platform**:
   - YouTube: `1920x1080`, 30fps
   - Instagram/TikTok: `1080x1920`, 30fps
   - High-end: `3840x2160` (4K), 60fps

## File Management

The script creates these files/directories:

- `_auto_tmp/` - Downloaded assets (can be deleted)
- `captions.vtt` - Generated captions (keep for reuse)
- `automation.log` - Detailed logs (useful for debugging)
- `output.mp4` - Your generated video

You can safely delete `_auto_tmp/` after video generation to save space.

## Getting Help

If you encounter issues:

1. Check `automation.log` for detailed error messages
2. Run with `--log-level DEBUG` for more information
3. Verify your API keys are correct in `.env`
4. Make sure ffmpeg is installed
5. Check that you have enough disk space

## API Rate Limits

Both Pexels and Pixabay have rate limits:

- **Pexels**: 200 requests/hour (free tier)
- **Pixabay**: 5,000 requests/hour (with API key)

The script automatically falls back between providers, so having both API keys helps avoid rate limits.

## Next Steps

Once you're comfortable with basic usage:

1. Experiment with different styles
2. Create custom query files for important projects
3. Try different resolutions and frame rates
4. Combine with video editing software for final touches
