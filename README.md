# YouTube Automation

Automated video generation from audio narration with stock footage from Pexels and Pixabay.

## Features

✅ **Automatic transcription** using Whisper AI  
✅ **Smart asset selection** with full-text queries for better relevance  
✅ **Multi-provider support** - Pexels and Pixabay video APIs  
✅ **Reduced clip repetition** - Searches both providers and randomizes selection  
✅ **Background music** - Adds classical/ambient music for better storytelling  
✅ **Image fallback** - Uses static images when videos aren't available  
✅ **No black screens** - Every segment has visual content  
✅ **Modular architecture** - Clean separation of concerns  
✅ **Comprehensive logging** - Track every asset selection  
✅ **Environment-based configuration** - Secure API key management  

## Quick Start

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/samiabat/youtube-automation.git
cd youtube-automation

# Install dependencies
pip install -r requirements.txt

# Download NLTK data
python -c "import nltk; nltk.download('punkt'); nltk.download('punkt_tab'); nltk.download('stopwords')"
```

### 2. Configuration

Copy the example environment file and add your API keys:

```bash
cp .env.example .env
```

Edit `.env` and add your API keys:

```env
PEXELS_API_KEY=your_pexels_api_key_here
PIXABAY_API_KEY=your_pixabay_api_key_here
```

**Get API Keys:**
- Pexels: https://www.pexels.com/api/
- Pixabay: https://pixabay.com/api/docs/

### 3. Usage

#### Basic usage with auto-transcription:

```bash
python main.py --audio narration.mp3 --autocaptions --out video.mp4
```

#### Use existing captions:

```bash
python main.py --audio narration.mp3 --captions captions.vtt --out video.mp4
```

#### Customize video settings:

```bash
python main.py \
  --audio narration.mp3 \
  --autocaptions \
  --resolution 1080x1920 \
  --fps 60 \
  --style cinematic \
  --out vertical_video.mp4
```

#### Use title for better query relevance:

```bash
python main.py \
  --audio narration.mp3 \
  --autocaptions \
  --title "Understanding the Solar System" \
  --style nature \
  --out solar_system.mp4
```

> **Tip:** The `--title` parameter helps keep video footage relevant to your main topic. When a segment mentions something unrelated (e.g., "like a football field" in a space video), the title keywords ensure the search still returns space-related content.

#### With custom queries for specific segments:

```bash
python main.py \
  --audio narration.mp3 \
  --captions captions.vtt \
  --custom-queries queries.json \
  --out video.mp4
```

#### With background music:

```bash
python main.py \
  --audio narration.mp3 \
  --autocaptions \
  --music-volume 0.15 \
  --out video_with_music.mp4
```

> **Note:** Background music is enabled by default at 10% volume. Use `--no-background-music` to disable it, or `--music-volume` to adjust the volume (0.0-1.0).

#### Disable background music:

```bash
python main.py \
  --audio narration.mp3 \
  --autocaptions \
  --no-background-music \
  --out video_no_music.mp4
```

## Command-Line Options

### Required Arguments

- `--audio PATH` - Path to narration audio file (mp3/wav)
- `--autocaptions` OR `--captions PATH` - Generate captions or use existing file

### Caption Options

- `--captions-out PATH` - Where to save generated captions (default: captions.vtt)
- `--whisper-model MODEL` - Whisper model: tiny, base, small, medium, large, large-v3
- `--device DEVICE` - Computation device: cpu, cuda, auto

### Output Options

- `--out PATH` - Output video path (default: output.mp4)
- `--resolution WxH` - Video resolution, e.g., 1920x1080 or 1080x1920
- `--fps N` - Frames per second (default: 30)

### Provider Options

- `--provider NAME` - Primary stock provider: pexels or pixabay
- `--fallback NAME` - Fallback stock provider: pexels or pixabay

### Style Options

- `--style STYLE` - Video style: general, cinematic, nature, tech
- `--title TEXT` - Video title for context - helps ensure queried assets stay relevant to the main topic
- `--custom-queries PATH` - JSON file with custom search queries per segment

### Feature Toggles

- `--no-subs` - Disable subtitle overlay
- `--transitions` - Enable crossfade transitions between clips
- `--no-background-music` - Disable background music (enabled by default)
- `--music-volume FLOAT` - Background music volume (0.0-1.0, default: 0.1 = 10%)

### Advanced Options

- `--min-seg SECONDS` - Minimum segment duration (default: 0.12)
- `--tmpdir PATH` - Temporary directory for downloads (default: _auto_tmp)
- `--log-level LEVEL` - Logging level: DEBUG, INFO, WARNING, ERROR

## Architecture

The codebase is organized into modular components:

```
youtube-automation/
├── main.py              # Main entry point and CLI
├── config.py            # Configuration and environment variables
├── transcribe.py        # Audio transcription with Whisper
├── download_assets.py   # Stock video/image providers
├── video_builder.py     # Video assembly and rendering
├── auto_video_backaup.py  # Legacy monolithic script (backup)
├── .env                 # Your API keys (not in git)
├── .env.example         # Template for .env
└── requirements.txt     # Python dependencies
```

### Key Improvements

1. **No More Black Screens**: Every segment gets a video, image, or meaningful fallback
2. **Better Content Relevance**: Uses full segment text for queries instead of just keywords
3. **Reduced Clip Repetition**: Combines results from both providers and uses randomized selection with URL tracking
4. **Background Music**: Automatically adds classical/ambient background music at low volume
5. **Smart Fallback Chain**: Video → Image → Simplified Query → Theme-based fallback
6. **Comprehensive Logging**: Track every asset selection decision
7. **Secure Configuration**: API keys in .env file, not in code
8. **Modular Design**: Easy to extend and maintain

## Custom Queries

Create a JSON file to override automatic query generation for specific segments:

```json
{
  "0": "sunrise over mountains",
  "5": "busy city street at night",
  "12": "close up of hands typing on keyboard"
}
```

Keys are segment indices (starting from 0), values are search queries.

## How Clip Variation Works

To avoid repetitive clips, the system now:

1. **Searches Multiple Providers**: Queries both Pexels and Pixabay simultaneously (if both API keys are configured)
2. **Increased Results**: Fetches up to 10 clips per query instead of just 3
3. **Randomized Selection**: Randomly selects from available clips instead of always picking the first one
4. **URL Tracking**: Keeps track of used URLs to avoid repeating the same clip
5. **Smart Fallback**: If all clips have been used, it will still select randomly to vary the order

This approach significantly reduces repetition and provides much more variety in your videos.

## Background Music

The system can automatically add classical/ambient background music to enhance storytelling:

- **Automatic Download**: Downloads royalty-free background music from free sources
- **Smart Looping**: Automatically loops music to match video duration
- **Volume Control**: Default volume is 10% (adjustable with `--music-volume`)
- **Graceful Fallback**: If music download fails, video generation continues without interruption

The background music is mixed with narration audio, creating a more professional and engaging result.

## Logging

All operations are logged to both console and `automation.log` file. Use `--log-level DEBUG` for detailed information about asset selection and processing.

Example log output:
```
2024-01-15 10:23:45 - video_builder - INFO - --- Processing segment 0 (0.00s - 3.50s, duration: 3.50s) ---
2024-01-15 10:23:45 - video_builder - INFO - Text: 'Welcome to our tutorial on machine learning'
2024-01-15 10:23:45 - video_builder - INFO - Generated query: 'Welcome to our tutorial on machine learning'
2024-01-15 10:23:46 - download_assets - INFO - Searching Pexels for: 'Welcome to our tutorial on machine learning'
2024-01-15 10:23:47 - download_assets - INFO - Pexels returned 3 video URLs
2024-01-15 10:23:47 - download_assets - INFO - Using video from primary provider
2024-01-15 10:23:48 - video_builder - INFO - Using video asset for segment 0
```

## Environment Variables

All settings can be configured via `.env` file:

```env
# Required: At least one API key
PEXELS_API_KEY=your_key
PIXABAY_API_KEY=your_key

# Optional: Whisper settings
WHISPER_MODEL=small
WHISPER_DEVICE=auto

# Optional: Video settings
DEFAULT_RESOLUTION=1920x1080
DEFAULT_FPS=30
DEFAULT_STYLE=general

# Optional: Provider preferences
PRIMARY_PROVIDER=pexels
FALLBACK_PROVIDER=pixabay

# Optional: Logging
LOG_LEVEL=INFO
```

## Troubleshooting

### No API keys error
Make sure you've created `.env` file and added at least one valid API key.

### NLTK data not found
Run: `python -c "import nltk; nltk.download('punkt'); nltk.download('stopwords')"`

### FFmpeg not found
Install ffmpeg: 
- Ubuntu/Debian: `sudo apt-get install ffmpeg`
- macOS: `brew install ffmpeg`
- Windows: Download from https://ffmpeg.org/

### Out of memory
Try reducing video resolution or using a smaller Whisper model.

## License

MIT License - See LICENSE file for details

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
