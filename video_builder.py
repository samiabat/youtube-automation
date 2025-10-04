"""
Video builder module.
Assembles final video from narration audio and stock assets.
"""
import os
import re
import random
import logging
from typing import List, Optional, Tuple
import json

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# Pillow compatibility shim for moviepy
try:
    Resampling = getattr(Image, "Resampling", None)
    if Resampling is not None and not hasattr(Image, "ANTIALIAS"):
        Image.ANTIALIAS = Resampling.LANCZOS  # keep MoviePy happy on Pillow≥10
except Exception:
    pass

# Video editing
from moviepy.editor import (
    AudioFileClip,
    VideoFileClip,
    ImageClip,
    CompositeVideoClip,
    concatenate_videoclips,
)
from moviepy.video.VideoClip import ColorClip

# NLP for query generation
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize

from transcribe import Segment
from download_assets import (
    make_provider, 
    fetch_asset_url, 
    download_asset,
    validate_asset,
    ImageFallbackProvider,
    download_background_music,
)
from config import Config

logger = logging.getLogger(__name__)

# Path to fallback assets (can be overridden)
FALLBACK_VIDEO_PATH = None
FALLBACK_IMAGE_PATH = None

# Ensure NLTK data is available
def _ensure_nltk():
    """Download required NLTK data if not already present."""
    try:
        nltk.data.find("tokenizers/punkt")
    except LookupError:
        nltk.download("punkt")
    try:
        nltk.data.find("tokenizers/punkt_tab")
    except Exception:
        try:
            nltk.download("punkt_tab")
        except Exception:
            pass
    try:
        nltk.data.find("corpora/stopwords")
    except LookupError:
        nltk.download("stopwords")

_ensure_nltk()

STOP = set(stopwords.words("english"))

# Theme-based fallback queries
THEME_MAP = {
    "cinematic": ["cinematic b-roll", "slow motion city", "moody landscape", "ocean waves", "aerial skyline"],
    "nature": ["forest canopy", "ocean reef", "mountain sunrise", "river flow", "desert dunes"],
    "tech": ["data center", "robot arm", "circuit board macro", "coding close-up", "neon city"],
    "general": ["city b-roll", "people walking", "clouds timelapse", "street night lights", "abstract background"],
}


def extract_keywords(text: str, topk: int = 4) -> List[str]:
    """Extract top keywords from text."""
    tokens = [w.lower() for w in word_tokenize(text) if re.match(r"^[a-zA-Z][a-zA-Z\-]+$", w)]
    tokens = [w for w in tokens if w not in STOP and len(w) > 2]
    freq = {}
    for w in tokens:
        freq[w] = freq.get(w, 0) + 1
    ranked = sorted(freq.items(), key=lambda x: (-x[1], x[0]))
    return [w for w, _ in ranked[:topk]] or tokens[:topk]


def generate_query_for_segment(seg: Segment, style: str, use_full_text: bool = True, title: Optional[str] = None) -> str:
    """
    Generate search query for a segment.
    
    Args:
        seg: The segment to generate query for
        style: Video style (cinematic, nature, tech, general)
        use_full_text: If True, use full segment text; if False, use keywords only
        title: Optional video title for context to ensure relevance
    
    Returns:
        Search query string
    """
    text = seg.text.strip()
    
    # Extract title keywords for context if title is provided
    title_keywords = []
    if title:
        title_keywords = extract_keywords(title, topk=2)
    
    if use_full_text and len(text) > 0:
        # Use full text as query for better relevance
        # Limit to first 100 chars to avoid overly long queries
        query = text[:100]
        
        # Add title keywords to ensure relevance to main topic
        if title_keywords:
            query = f"{' '.join(title_keywords)} {query}"
        
        logger.debug(f"Segment {seg.idx}: Using full text query: '{query}'")
        return query
    else:
        # Fallback to keyword extraction
        kws = extract_keywords(text, topk=4)
        if not kws:
            # Use theme-based fallback, with title context if available
            query = random.choice(THEME_MAP.get(style, THEME_MAP["general"]))
            if title_keywords:
                query = f"{' '.join(title_keywords)} {query}"
            logger.debug(f"Segment {seg.idx}: No keywords, using theme fallback: '{query}'")
            return query
        
        # Combine title keywords with segment keywords for relevance
        if title_keywords:
            kws = title_keywords + kws[:2]  # Use top 2 title keywords + top 2 segment keywords
        
        query = " ".join(kws)
        if style in ("cinematic", "nature", "tech"):
            query += f" {style}"
        
        logger.debug(f"Segment {seg.idx}: Using keyword query: '{query}'")
        return query


def simplify_query(query: str, style: str, title: Optional[str] = None) -> str:
    """
    Simplify a query that failed to get results.
    Extracts main keywords and adds style.
    
    Args:
        query: The original query that failed
        style: Video style
        title: Optional video title for context
    
    Returns:
        Simplified query string
    """
    kws = extract_keywords(query, topk=2)
    
    # Add title keywords to maintain relevance if provided
    title_keywords = []
    if title:
        title_keywords = extract_keywords(title, topk=2)
    
    if kws:
        # Combine title keywords with simplified query keywords
        if title_keywords:
            simplified = " ".join(title_keywords + kws[:1])  # Title keywords + 1 main keyword
        else:
            simplified = " ".join(kws)
        
        if style in ("cinematic", "nature", "tech"):
            simplified += f" {style}"
        return simplified
    
    # Ultimate fallback with title context if available
    fallback = random.choice(THEME_MAP.get(style, THEME_MAP["general"]))
    if title_keywords:
        fallback = f"{' '.join(title_keywords)} {fallback}"
    return fallback


def validate_video_clip(path: str) -> bool:
    """
    Validate that a video file is readable and has valid duration.
    
    Args:
        path: Path to video file
        
    Returns:
        True if video is valid, False otherwise
    """
    try:
        from moviepy.editor import VideoFileClip
        clip = VideoFileClip(path, has_mask=False)
        duration = clip.duration
        clip.close()
        
        if duration <= 0:
            logger.warning(f"Video has invalid duration ({duration}s): {path}")
            return False
        
        logger.debug(f"Video validated: {path} (duration: {duration:.2f}s)")
        return True
    except Exception as e:
        logger.warning(f"Failed to validate video {path}: {e}")
        return False


def extend_clip_to_duration(clip, target_duration: float):
    """
    Extend a clip to match target duration by looping or freezing last frame.
    
    Args:
        clip: VideoFileClip or ImageClip to extend
        target_duration: Target duration in seconds
        
    Returns:
        Extended clip
    """
    if clip.duration >= target_duration:
        return clip
    
    # For very short clips (< 0.5s), use freeze frame on last frame
    if clip.duration < 0.5:
        logger.info(f"Clip is very short ({clip.duration:.2f}s), using freeze frame")
        try:
            # Get the last frame and extend it
            from moviepy.video.fx.all import freeze
            frozen = freeze(clip, t=clip.duration - 0.01, freeze_duration=target_duration)
            return frozen
        except Exception as e:
            logger.warning(f"Failed to freeze frame: {e}, using loop instead")
    
    # For longer clips, loop them
    logger.info(f"Extending clip from {clip.duration:.2f}s to {target_duration:.2f}s by looping")
    try:
        # Calculate how many loops we need
        loops_needed = int(target_duration / clip.duration) + 1
        from moviepy.editor import concatenate_videoclips
        looped = concatenate_videoclips([clip] * loops_needed, method="compose")
        return looped.subclip(0, target_duration)
    except Exception as e:
        logger.error(f"Failed to loop clip: {e}")
        return clip


def create_fallback_clip(w: int, h: int, duration: float, text: str = "") -> 'VideoClip':
    """
    Create a fallback clip when no asset is available.
    Uses a colored gradient background instead of black screen.
    
    Args:
        w: Width
        h: Height  
        duration: Duration in seconds
        text: Optional text to display
        
    Returns:
        VideoClip with gradient background
    """
    logger.info(f"Creating fallback clip with gradient background (duration: {duration:.2f}s)")
    
    try:
        # Create a simple gradient background
        gradient_img = Image.new("RGB", (w, h))
        pixels = gradient_img.load()
        
        # Create a blue-to-purple gradient
        for y in range(h):
            r = int(30 + (y / h) * 50)  # 30 to 80
            g = int(30 + (y / h) * 30)  # 30 to 60
            b = int(60 + (y / h) * 80)  # 60 to 140
            for x in range(w):
                pixels[x, y] = (r, g, b)
        
        gradient_array = np.asarray(gradient_img)
        bg = ImageClip(gradient_array).set_duration(duration)
        
        # Add text if provided
        if text:
            txt_clip = make_subtitle_clip(f"[{text}]", w, h, fontsize=48)
            if txt_clip is not None:
                return CompositeVideoClip([bg, txt_clip.set_duration(duration)], size=(w, h))
        
        return bg
    except Exception as e:
        logger.error(f"Failed to create gradient fallback: {e}, using solid color")
        # Ultimate fallback - dark blue solid color
        return ColorClip(size=(w, h), color=(30, 40, 80)).set_duration(duration)


def ensure_resolution(clip, w: int, h: int, fit: str = "cover"):
    """
    Resize and crop clip to target resolution.
    Handles both landscape and portrait clips properly.
    """
    if fit == "cover":
        # Calculate aspect ratios
        clip_aspect = clip.w / clip.h
        target_aspect = w / h
        
        # Determine if we need to scale by width or height
        if clip_aspect > target_aspect:
            # Clip is wider, scale by height
            scaled = clip.resize(height=h)
        else:
            # Clip is taller or same aspect, scale by width
            scaled = clip.resize(width=w)
        
        # Crop to exact size
        cropped = scaled.crop(x_center=scaled.w/2, y_center=scaled.h/2, width=w, height=h)
        return cropped
    else:
        return clip.resize(newsize=(w, h))


def _find_font_path() -> Optional[str]:
    """Find a suitable font for subtitle rendering."""
    candidates = [
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Helvetica.ttc",
        "/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def _wrap_lines(draw, text: str, font, max_width: int) -> List[str]:
    """Wrap text into multiple lines based on max width."""
    words = text.split()
    lines, line = [], ""
    for w in words:
        test = (line + " " + w).strip()
        if draw.textlength(test, font=font) <= max_width:
            line = test
        else:
            if line:
                lines.append(line)
            line = w
    if line:
        lines.append(line)
    return lines


def make_subtitle_clip(text: str, w: int, h: int, fontsize: int = 50, pad: int = 22):
    """
    Create a subtitle clip with text overlay.
    Returns None if text is empty.
    """
    if not text or not text.strip():
        return None
    
    font_path = _find_font_path()
    try:
        font = ImageFont.truetype(font_path, fontsize) if font_path else ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()
    
    max_text_width = max(10, int(w * 0.9))
    dummy = Image.new("RGB", (10, 10))
    draw = ImageDraw.Draw(dummy)
    lines = _wrap_lines(draw, text, font, max_text_width)
    
    ascent, descent = font.getmetrics()
    line_h = max(2, ascent + descent)
    gap = max(1, int(line_h * 0.25))
    text_h = max(0, len(lines) * line_h + max(0, len(lines) - 1) * gap)
    text_w = 0
    for ln in lines:
        text_w = max(text_w, int(draw.textlength(ln, font=font)))
    
    box_w = max(2, min(max_text_width, text_w + 2 * pad))
    box_h = max(2, text_h + 2 * pad)
    
    rgb = Image.new("RGB", (box_w, box_h), (0, 0, 0))
    draw_rgb = ImageDraw.Draw(rgb)
    mask = Image.new("L", (box_w, box_h), int(0.6 * 255))
    draw_m = ImageDraw.Draw(mask)
    
    y = pad
    for ln in lines:
        tw = int(draw.textlength(ln, font=font))
        x = max(0, (box_w - tw) // 2)
        draw_m.text((x, y), ln, font=font, fill=255)
        draw_rgb.text((x, y), ln, font=font, fill=(255, 255, 255))
        y += line_h + gap
    
    rgb_arr = np.asarray(rgb)
    mask_arr = np.asarray(mask, dtype=np.float32) / 255.0
    txt_clip = ImageClip(rgb_arr).set_position(("center", int(h * 0.82)))
    mask_clip = ImageClip(mask_arr, ismask=True).set_position(("center", int(h * 0.82)))
    txt_clip = txt_clip.set_mask(mask_clip)
    return txt_clip


def build_video(audio_path: str,
                segments: List[Segment],
                out_path: str,
                provider_name: Optional[str] = None,
                fallback_name: Optional[str] = None,
                resolution: Tuple[int, int] = (1920, 1080),
                fps: int = 30,
                style: str = "general",
                subs: bool = True,
                transitions: bool = False,
                custom_queries_path: Optional[str] = None,
                title: Optional[str] = None,
                tmpdir: str = "_auto_tmp",
                background_music: bool = True,
                music_volume: float = 0.1):
    """
    Build the final video from audio and segments.
    
    Args:
        audio_path: Path to narration audio file
        segments: List of timed text segments
        out_path: Output video path
        provider_name: Primary video provider name
        fallback_name: Fallback video provider name
        resolution: Video resolution (width, height)
        fps: Frames per second
        style: Video style for query generation
        subs: Whether to add subtitles
        transitions: Whether to add crossfade transitions
        custom_queries_path: Optional JSON file with custom queries per segment
        title: Optional video title for query context to ensure relevance
        tmpdir: Temporary directory for downloads
        background_music: Whether to add background music (default: True)
        music_volume: Volume of background music relative to narration (default: 0.1 = 10%)
    """
    logger.info(f"Building video: {out_path}")
    logger.info(f"Resolution: {resolution[0]}x{resolution[1]}, FPS: {fps}, Style: {style}")
    if title:
        logger.info(f"Video title (for context): '{title}'")
    
    narration = AudioFileClip(audio_path)
    total_dur = narration.duration
    logger.info(f"Audio duration: {total_dur:.2f}s, Segments: {len(segments)}")
    
    # Initialize providers
    primary = make_provider(provider_name or Config.PRIMARY_PROVIDER)
    fallback = make_provider(fallback_name or Config.FALLBACK_PROVIDER)
    
    # Initialize image fallback
    image_fallback = None
    if Config.PEXELS_API_KEY:
        try:
            image_fallback = ImageFallbackProvider(provider_type="pexels")
        except Exception as e:
            logger.warning(f"Failed to initialize Pexels image fallback: {e}")
    
    if not image_fallback and Config.PIXABAY_API_KEY:
        try:
            image_fallback = ImageFallbackProvider(provider_type="pixabay")
        except Exception as e:
            logger.warning(f"Failed to initialize Pixabay image fallback: {e}")
    
    # Load custom queries if provided
    custom_queries = {}
    if custom_queries_path and os.path.exists(custom_queries_path):
        with open(custom_queries_path, "r", encoding="utf-8") as f:
            custom_queries = json.load(f)
        logger.info(f"Loaded {len(custom_queries)} custom queries")
    
    w, h = resolution
    built_clips = []
    
    # Track used URLs to avoid repetition
    used_urls = set()
    
    for seg in segments:
        logger.info(f"\n--- Processing segment {seg.idx} ({seg.start:.2f}s - {seg.end:.2f}s, duration: {seg.dur:.2f}s) ---")
        logger.info(f"Text: '{seg.text}'")
        
        # Get query (custom or generated)
        if str(seg.idx) in custom_queries:
            query = custom_queries[str(seg.idx)]
            logger.info(f"Using custom query: '{query}'")
        else:
            query = generate_query_for_segment(seg, style, use_full_text=True, title=title)
            logger.info(f"Generated query: '{query}'")
        
        # Fetch asset URL
        url, asset_type = fetch_asset_url(query, primary, fallback, image_fallback, used_urls)
        
        # If no results, try simplified query
        if not url:
            logger.warning(f"No results for query '{query}', trying simplified query")
            simplified_query = simplify_query(query, style, title=title)
            logger.info(f"Simplified query: '{simplified_query}'")
            url, asset_type = fetch_asset_url(simplified_query, primary, fallback, image_fallback, used_urls)
        
        # Build clip based on asset type
        if not url or asset_type == "none":
            # Ultimate fallback: gradient background with query text
            logger.warning(f"No assets found, using fallback clip for segment {seg.idx}")
            clip = create_fallback_clip(w, h, seg.dur, query)
        elif asset_type == "image":
            # Use image as static clip
            logger.info(f"Using image asset for segment {seg.idx}")
            try:
                img_path = download_asset(url, tmpdir)
                img_clip = ImageClip(img_path).set_duration(seg.dur)
                img_clip = ensure_resolution(img_clip, w, h, fit="cover")
                clip = img_clip
            except Exception as e:
                logger.error(f"Failed to load image: {e}, using fallback clip")
                clip = create_fallback_clip(w, h, seg.dur, query)
        else:
            # Use video clip
            logger.info(f"Using video asset for segment {seg.idx}")
            try:
                path = download_asset(url, tmpdir)
                
                # Validate video before using
                if not validate_video_clip(path):
                    logger.error(f"Video validation failed for {path}, trying next asset or fallback")
                    # Try to get another asset from the same query
                    clip = create_fallback_clip(w, h, seg.dur, query)
                else:
                    base = VideoFileClip(path, has_mask=False).without_audio()
                    
                    # Check if video needs to be extended
                    if base.duration < seg.dur:
                        logger.warning(f"Video duration ({base.duration:.2f}s) is shorter than segment ({seg.dur:.2f}s)")
                        base = extend_clip_to_duration(base, seg.dur)
                    
                    # Cut video to segment duration
                    if base.duration <= seg.dur + 0.2:
                        sub = base
                    else:
                        max_start = max(0, base.duration - seg.dur)
                        start_t = random.uniform(0, max_start)
                        sub = base.subclip(start_t, start_t + seg.dur)
                    
                    sub = ensure_resolution(sub, w, h, fit="cover")
                    clip = sub
            except Exception as e:
                logger.error(f"Failed to load video: {e}, using fallback clip")
                clip = create_fallback_clip(w, h, seg.dur, query)
        
        # Add subtitles if enabled
        if subs:
            sclip = make_subtitle_clip(seg.text, w, h)
            if sclip is not None:
                sclip = sclip.set_duration(seg.dur)
                clip = CompositeVideoClip([clip, sclip], size=(w, h))
        
        built_clips.append(clip.set_duration(seg.dur))
        logger.info(f"Segment {seg.idx} complete")
    
    # Concatenate clips with optional transitions
    logger.info("\nConcatenating clips...")
    if transitions and len(built_clips) > 1:
        seq = [built_clips[0]]
        for nxt in built_clips[1:]:
            a = seq[-1]
            base_overlap = 6.0 / fps
            safe_overlap = min(base_overlap, 0.25, a.duration * 0.25, nxt.duration * 0.25)
            if safe_overlap < (1.0 / fps):
                seq.append(nxt)
                continue
            seq[-1] = a.crossfadeout(safe_overlap)
            seq.append(nxt.crossfadein(safe_overlap))
        video = concatenate_videoclips(seq, method="compose")
    else:
        video = concatenate_videoclips(built_clips, method="compose")
    
    # Ensure video duration matches audio
    if video.duration > total_dur:
        logger.info(f"Trimming video from {video.duration:.2f}s to {total_dur:.2f}s")
        video = video.subclip(0, total_dur)
    elif video.duration < total_dur:
        logger.info(f"Padding video from {video.duration:.2f}s to {total_dur:.2f}s")
        pad = ColorClip(size=(w, h), color=(0, 0, 0)).set_duration(total_dur - video.duration)
        video = concatenate_videoclips([video, pad], method="compose")
    
    # Add audio and export
    logger.info("Adding audio and exporting video...")
    
    # Mix narration with background music if enabled
    if background_music:
        logger.info("Downloading and mixing background music...")
        bg_music_path = download_background_music(tmpdir, total_dur)
        
        if bg_music_path:
            try:
                from moviepy.audio.fx.all import volumex
                from moviepy.editor import CompositeAudioClip
                
                # Load background music
                bg_audio = AudioFileClip(bg_music_path)
                
                # Loop or trim background music to match video duration
                if bg_audio.duration < total_dur:
                    # Loop the music
                    loops_needed = int(total_dur / bg_audio.duration) + 1
                    from moviepy.editor import concatenate_audioclips
                    bg_audio_looped = concatenate_audioclips([bg_audio] * loops_needed)
                    bg_audio = bg_audio_looped.subclip(0, total_dur)
                else:
                    # Trim to video duration
                    bg_audio = bg_audio.subclip(0, total_dur)
                
                # Reduce volume of background music
                bg_audio = bg_audio.fx(volumex, music_volume)
                
                # Mix narration and background music
                mixed_audio = CompositeAudioClip([narration, bg_audio])
                final = video.set_audio(mixed_audio)
                
                logger.info(f"Background music mixed at {int(music_volume * 100)}% volume")
                
            except Exception as e:
                logger.error(f"Failed to mix background music: {e}, using narration only")
                final = video.set_audio(narration)
        else:
            logger.warning("Background music download failed, using narration only")
            final = video.set_audio(narration)
    else:
        final = video.set_audio(narration)
    
    final.write_videofile(out_path, fps=fps, codec="libx264", audio_codec="aac", 
                         threads=4, preset="medium")
    
    logger.info(f"Video build complete: {out_path}")
