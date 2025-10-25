#!/usr/bin/env python3
"""
YouTube Automation - Main Script
Orchestrates the video generation pipeline.
"""
import argparse
import logging
import os
import sys
import re
from typing import Tuple

from config import Config
from transcribe import transcribe_audio, load_segments, Segment
from video_builder import build_video

# Configure logging
def setup_logging(level: str = "INFO"):
    """Setup logging configuration."""
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        numeric_level = logging.INFO
    
    logging.basicConfig(
        level=numeric_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('automation.log', mode='w')
        ]
    )

logger = logging.getLogger(__name__)


def parse_resolution(s: str) -> Tuple[int, int]:
    """Parse resolution string like '1920x1080' into tuple."""
    m = re.match(r"^(\d+)x(\d+)$", s)
    if not m:
        raise argparse.ArgumentTypeError("Resolution must be in format: WIDTHxHEIGHT (e.g., 1920x1080)")
    return int(m.group(1)), int(m.group(2))


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="YouTube Automation - Generate videos from audio narration with stock footage",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate captions and video in one go:
  python main.py --audio narration.mp3 --autocaptions --out video.mp4

  # Use existing captions:
  python main.py --audio narration.mp3 --captions captions.vtt --out video.mp4
  
  # Customize video settings:
  python main.py --audio narration.mp3 --autocaptions --resolution 1080x1920 --style cinematic --fps 60
        """
    )
    
    # Required arguments
    parser.add_argument("--audio", required=True, 
                       help="Path to narration audio file (mp3/wav)")
    
    # Caption options
    caption_group = parser.add_mutually_exclusive_group(required=True)
    caption_group.add_argument("--captions", 
                              help="Path to existing caption file (.vtt or .srt)")
    caption_group.add_argument("--autocaptions", action="store_true",
                              help="Auto-generate captions from audio using Whisper")
    
    parser.add_argument("--captions-out", default="captions.vtt",
                       help="Output path for generated captions (default: captions.vtt)")
    parser.add_argument("--whisper-model", 
                       choices=["tiny", "base", "small", "medium", "large", "large-v3"],
                       help="Whisper model size (default: from config or 'small')")
    parser.add_argument("--device", choices=["cpu", "cuda", "auto"],
                       help="Device for Whisper (default: from config or 'auto')")
    
    # Output options
    parser.add_argument("--out", default="output.mp4",
                       help="Output video path (default: output.mp4)")
    parser.add_argument("--resolution", type=parse_resolution,
                       help="Video resolution, e.g., 1920x1080 or 1080x1920 (default: from config)")
    parser.add_argument("--fps", type=int,
                       help="Frames per second (default: from config or 30)")
    
    # Provider options
    parser.add_argument("--provider", choices=["pexels", "pixabay"],
                       help="Primary stock provider (default: from config or 'pexels')")
    parser.add_argument("--fallback", choices=["pexels", "pixabay"],
                       help="Fallback stock provider (default: from config or 'pixabay')")
    
    # Style and customization
    parser.add_argument("--style", choices=["general", "cinematic", "nature", "tech"],
                       help="Video style for asset selection (default: from config or 'general')")
    parser.add_argument("--title",
                       help="Video title for context - helps ensure queried assets stay relevant to the main topic")
    parser.add_argument("--custom-queries", 
                       help="Path to JSON file with custom search queries per segment")
    
    # Feature toggles
    parser.add_argument("--no-subs", dest="subs", action="store_false", default=True,
                       help="Disable subtitles overlay")
    parser.add_argument("--transitions", action="store_true", default=False,
                       help="Enable crossfade transitions between clips")
    
    # Advanced options
    parser.add_argument("--min-seg", type=float, default=0.12,
                       help="Minimum segment duration in seconds (default: 0.12)")
    parser.add_argument("--tmpdir", default="_auto_tmp",
                       help="Temporary directory for downloads (default: _auto_tmp)")
    parser.add_argument("--log-level", 
                       choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                       help="Logging level (default: from config or INFO)")
    
    args = parser.parse_args()
    
    # Setup logging
    log_level = args.log_level or Config.LOG_LEVEL
    setup_logging(log_level)
    
    logger.info("=" * 60)
    logger.info("YouTube Automation - Video Generation Pipeline")
    logger.info("=" * 60)
    logger.info("Using YouTube as video source (no API keys required)")
    
    # Validate audio file
    if not os.path.exists(args.audio):
        logger.error(f"Audio file not found: {args.audio}")
        sys.exit(1)
    
    logger.info(f"Audio file: {args.audio}")
    
    # Step 1: Get or generate captions
    if args.autocaptions:
        logger.info("\n" + "=" * 60)
        logger.info("STEP 1: Transcribing Audio")
        logger.info("=" * 60)
        segments = transcribe_audio(
            audio_path=args.audio,
            out_path=args.captions_out,
            model_size=args.whisper_model,
            device=args.device
        )
    else:
        logger.info("\n" + "=" * 60)
        logger.info("STEP 1: Loading Existing Captions")
        logger.info("=" * 60)
        if not os.path.exists(args.captions):
            logger.error(f"Caption file not found: {args.captions}")
            sys.exit(1)
        segments = load_segments(args.captions)
    
    if not segments:
        logger.error("No segments found in captions!")
        sys.exit(1)
    
    logger.info(f"Loaded {len(segments)} segments")
    
    # Clamp minimum segment duration
    if args.min_seg and args.min_seg > 0:
        logger.info(f"Clamping minimum segment duration to {args.min_seg}s")
        clamped = []
        for s in segments:
            if s.end - s.start < args.min_seg:
                s = Segment(s.idx, s.start, s.start + args.min_seg, s.text)
            clamped.append(s)
        segments = clamped
    
    # Step 2: Build video
    logger.info("\n" + "=" * 60)
    logger.info("STEP 2: Building Video")
    logger.info("=" * 60)
    
    # Get settings from args or config
    resolution = args.resolution
    if not resolution:
        res_str = Config.DEFAULT_RESOLUTION
        resolution = parse_resolution(res_str)
    
    fps = args.fps or Config.DEFAULT_FPS
    style = args.style or Config.DEFAULT_STYLE
    provider = args.provider or Config.PRIMARY_PROVIDER
    fallback = args.fallback or Config.FALLBACK_PROVIDER
    
    build_video(
        audio_path=args.audio,
        segments=segments,
        out_path=args.out,
        provider_name=provider,
        fallback_name=fallback,
        resolution=resolution,
        fps=fps,
        style=style,
        subs=args.subs,
        transitions=args.transitions,
        custom_queries_path=args.custom_queries,
        title=args.title,
        tmpdir=args.tmpdir
    )
    
    logger.info("\n" + "=" * 60)
    logger.info("✓ Video generation complete!")
    logger.info(f"✓ Output: {args.out}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
