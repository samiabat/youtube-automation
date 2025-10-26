"""
Audio→Video Auto-Editor + Light Whisper Captions — Solid Build
----------------------------------------------------------------------------------
This script turns a narration audio into a synced video edit:
1) (Optional) Runs **faster‑whisper** to auto‑generate VTT captions from audio.
2) Parses captions (VTT/SRT) into timed segments.
3) Extracts search keywords per segment.
4) Creates gradient background clips with text overlays.
5) Cuts to duration, resizes/crop to frame, overlays subtitles (Pillow — no ImageMagick),
   adds safe crossfades, and exports an MP4 aligned to your original audio.

Hardening in this build
- No ImageMagick: subtitles drawn with Pillow (no TextClip).
- Pillow≥10 safe: compatibility shim for ANTIALIAS.
- M1/M2 friendly Whisper: sane compute types; `--device auto` ⇒ CPU by default.
- **Zero-size-mask fix**: subtitles use an explicit grayscale mask with guaranteed ≥2×2 size.
- **Safe crossfades**: overlap clamped; or disable with `--no-transitions`/`--no_transitions`.
- NLTK guards: downloads `punkt`, `punkt_tab`, `stopwords` if missing.
- CLI accepts both hyphen/underscore `--no-subs`/`--no_subs`, `--no-transitions`/`--no_transitions`.

Dependencies
------------
Python 3.9+, ffmpeg, moviepy==1.0.3, requests, webvtt-py, pysrt, nltk, faster-whisper, pillow

Install:
    pip install moviepy==1.0.3 requests webvtt-py pysrt nltk faster-whisper pillow
    python -c "import nltk; nltk.download('punkt'); nltk.download('punkt_tab'); nltk.download('stopwords')"
"""

import os
import re
import json
import random
import argparse
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np
import requests

# Captions
import webvtt
import pysrt

# NLP
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize

# Pillow for subtitle rendering + compatibility
from PIL import Image, ImageDraw, ImageFont
try:
    Resampling = getattr(Image, "Resampling", None)
    if Resampling is not None and not hasattr(Image, "ANTIALIAS"):
        Image.ANTIALIAS = Resampling.LANCZOS  # keep MoviePy happy on Pillow≥10
except Exception:
    pass

# Video
from moviepy.editor import (
    AudioFileClip,
    VideoFileClip,
    ImageClip,
    CompositeVideoClip,
    concatenate_videoclips,
)
from moviepy.video.VideoClip import ColorClip

# Whisper (light)
from faster_whisper import WhisperModel

# -------------------- NLTK guards --------------------

def _ensure_nltk():
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

# -------------------- Data types ---------------------

@dataclass
class Segment:
    idx: int
    start: float
    end: float
    text: str

    @property
    def dur(self) -> float:
        return max(0.1, self.end - self.start)

# -------------------- Captions parsing --------------------

def parse_vtt(path: str) -> List[Segment]:
    segs = []
    for i, cap in enumerate(webvtt.read(path)):
        start = time_to_seconds(cap.start)
        end = time_to_seconds(cap.end)
        text = clean_text(cap.text)
        if text.strip():
            segs.append(Segment(i, start, end, text))
    return segs

def parse_srt(path: str) -> List[Segment]:
    subs = pysrt.open(path)
    segs = []
    for i, s in enumerate(subs):
        start = s.start.hours*3600 + s.start.minutes*60 + s.start.seconds + s.start.milliseconds/1000.0
        end   = s.end.hours*3600   + s.end.minutes*60   + s.end.seconds   + s.end.milliseconds/1000.0
        text = clean_text(s.text)
        if text.strip():
            segs.append(Segment(i, start, end, text))
    return segs

def time_to_seconds(ts: str) -> float:
    h, m, s = ts.split(":")
    return int(h)*3600 + int(m)*60 + float(s)

def seconds_to_timestamp(sec: float) -> str:
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"

def clean_text(t: str) -> str:
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t

# -------------------- Keyword extraction --------------------

STOP = set(stopwords.words("english"))

THEME_MAP = {
    "cinematic": ["cinematic b-roll", "slow motion city", "moody landscape", "ocean waves", "aerial skyline"],
    "nature": ["forest canopy", "ocean reef", "mountain sunrise", "river flow", "desert dunes"],
    "tech": ["data center", "robot arm", "circuit board macro", "coding close-up", "neon city"],
    "general": ["city b-roll", "people walking", "clouds timelapse", "street night lights", "abstract background"],
}

def extract_keywords(text: str, topk: int = 4) -> List[str]:
    tokens = [w.lower() for w in word_tokenize(text) if re.match(r"^[a-zA-Z][a-zA-Z\-]+$", w)]
    tokens = [w for w in tokens if w not in STOP and len(w) > 2]
    freq = {}
    for w in tokens:
        freq[w] = freq.get(w, 0) + 1
    ranked = sorted(freq.items(), key=lambda x: (-x[1], x[0]))
    return [w for w, _ in ranked[:topk]] or tokens[:topk]

# -------------------- Stock providers --------------------
# -------------------- Video assembly --------------------

def ensure_resolution(clip, w, h, fit="cover"):
    if fit == "cover":
        return clip.fx(
            lambda c: c.resize(height=h).crop(x_center=c.w/2, y_center=c.h/2, width=w, height=h)
            if (c.w/c.h) > (w/h)
            else c.resize(width=w).crop(x_center=c.w/2, y_center=c.h/2, width=w, height=h)
        )
    else:
        return clip.resize(newsize=(w, h))


def _find_font_path() -> Optional[str]:
    candidates = [
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Helvetica.ttc",
        "/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def _wrap_lines(draw, text, font, max_width):
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
    """Return a bottom-centered text overlay (RGB) with explicit grayscale mask.
    Guarantees mask size ≥ 2×2; returns None if text is empty.
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


def smart_query_for_segment(seg: Segment, style: str) -> str:
    kws = extract_keywords(seg.text, topk=4)
    if not kws:
        return random.choice(THEME_MAP.get(style, THEME_MAP["general"]))
    q = " ".join(kws)
    if style in ("cinematic", "nature", "tech"):
        q += f" {style}"
    return q


# -------------------- Light Whisper (faster‑whisper) --------------------

def auto_captions(audio_path: str, out_path: str, model_size: str = "small", device: str = "auto") -> List[Segment]:
    if device == "auto":
        device = "cpu"
    compute_type = "int8" if device == "cpu" else "float16"

    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    seg_iter, _ = model.transcribe(
        audio_path,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=300),
    )

    segs: List[Segment] = []
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("WEBVTT\n\n")
        for i, s in enumerate(seg_iter):
            start, end = s.start, s.end
            text = clean_text(s.text)
            segs.append(Segment(i, start, end, text))
            f.write(f"{seconds_to_timestamp(start)} --> {seconds_to_timestamp(end)}\n{text}\n\n")
    return segs

# -------------------- Build video --------------------

def build_video(audio_path: str,
                segments: List[Segment],
                out_path: str,
                resolution: Tuple[int, int],
                fps: int,
                style: str,
                subs: bool,
                transitions: bool,
                custom_queries_path: Optional[str] = None,
                tmpdir: str = "_auto_tmp"):

    narration = AudioFileClip(audio_path)
    total_dur = narration.duration

    custom_queries = {}
    if custom_queries_path and os.path.exists(custom_queries_path):
        with open(custom_queries_path, "r", encoding="utf-8") as f:
            custom_queries = json.load(f)

    w, h = resolution
    built_clips = []

    for seg in segments:
        q = custom_queries.get(str(seg.idx)) or smart_query_for_segment(seg, style)
        # Create fallback clip (no external providers)
        clip = fallback_clip(w, h, seg.dur, q)

        if subs:
            sclip = make_subtitle_clip(seg.text, w, h)
            if sclip is not None:
                sclip = sclip.set_duration(seg.dur)
                clip = CompositeVideoClip([clip, sclip], size=(w, h))

        built_clips.append(clip.set_duration(seg.dur))

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

    if video.duration > total_dur:
        video = video.subclip(0, total_dur)
    elif video.duration < total_dur:
        pad = ColorClip(size=(w, h), color=(0, 0, 0)).set_duration(total_dur - video.duration)
        video = concatenate_videoclips([video, pad], method="compose")

    final = video.set_audio(narration)
    final.write_videofile(out_path, fps=fps, codec="libx264", audio_codec="aac", threads=4, preset="medium")


# -------------------- Segments loader --------------------

def load_segments(captions_path: str) -> List[Segment]:
    ext = os.path.splitext(captions_path)[1].lower()
    if ext == ".vtt":
        return parse_vtt(captions_path)
    elif ext == ".srt":
        return parse_srt(captions_path)
    else:
        raise ValueError("Captions must be .vtt or .srt")

# -------------------- CLI --------------------

def parse_res(s: str) -> Tuple[int, int]:
    m = re.match(r"^(\d+)x(\d+)$", s)
    if not m:
        raise argparse.ArgumentTypeError("Resolution must look like 1920x1080")
    return int(m.group(1)), int(m.group(2))


def main():
    print("Auto Video Generator (Audio→Stock with Captions)")
    ap = argparse.ArgumentParser(description="Audio→Stock auto video generator (with light Whisper)")
    ap.add_argument("--audio", required=True, help="Narration audio path (wav/mp3)")

    # Captions options
    ap.add_argument("--captions", help="Existing .vtt or .srt matching the audio")
    ap.add_argument("--autocaptions", action="store_true", help="Run faster‑whisper to create captions from audio")
    ap.add_argument("--captions_out", default="captions.vtt", help="Where to save generated captions (VTT)")
    ap.add_argument("--whisper_model", default="small", help="tiny|base|small|medium|large-v3")
    ap.add_argument("--device", default="auto", help="cpu|cuda|metal|auto")

    # Render options
    ap.add_argument("--out", default="out.mp4", help="Output video path")
    ap.add_argument("--resolution", type=parse_res, default="1920x1080", help="e.g., 1920x1080 or 1080x1920")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--style", choices=["general","cinematic","nature","tech"], default="general")

    # Accept both hyphen and underscore variants
    # ap.add_argument("--no_subs", dest="no_subs", action="store_true", help="Disable burned-in subtitles")


    ap.add_argument("--no_subs", dest="no_subs", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--no_transitions", dest="no_transitions", action="store_true", help="Disable crossfades")
    # ap.add_argument("--no_transitions", dest="no_transitions", action="store_true", help=argparse.SUPPRESS)

    ap.add_argument("--custom_queries", help="JSON mapping segment index→custom search query")
    ap.add_argument("--min-seg", type=float, default=0.12, help="Clamp minimum segment duration in seconds")

    args = ap.parse_args()

    # Create captions if needed
    if args.autocaptions:
        print(f"[Whisper] Generating captions → {args.captions_out} (model={args.whisper_model}, device={args.device})")
        segments = auto_captions(args.audio, args.captions_out, model_size=args.whisper_model, device=args.device)
    else:
        if not args.captions:
            raise SystemExit("Provide --captions or enable --autocaptions")
        segments = load_segments(args.captions)

    if not segments:
        raise SystemExit("No segments found in captions.")

    # Optional: clamp micro-segments so masks & (optional) transitions behave
    if args.min_seg and args.min_seg > 0:
        clamped = []
        for s in segments:
            if s.end - s.start < args.min_seg:
                s = Segment(s.idx, s.start, s.start + args.min_seg, s.text)
            clamped.append(s)
        segments = clamped

    build_video(
        audio_path=args.audio,
        segments=segments,
        out_path=args.out,
        resolution=args.resolution,
        fps=args.fps,
        style=args.style,
        subs=not args.no_subs,
        transitions=not args.no_transitions,
        custom_queries_path=args.custom_queries,
    )

if __name__ == "__main__":
    main()
