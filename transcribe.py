"""
Transcription module using faster-whisper.
Handles audio transcription and caption generation.
"""
import logging
from dataclasses import dataclass
from typing import List
import os

from faster_whisper import WhisperModel
import webvtt
import pysrt
import re

from config import Config

logger = logging.getLogger(__name__)


@dataclass
class Segment:
    """Represents a timed text segment."""
    idx: int
    start: float
    end: float
    text: str

    @property
    def dur(self) -> float:
        return max(0.1, self.end - self.start)


def clean_text(t: str) -> str:
    """Remove HTML tags and normalize whitespace."""
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def time_to_seconds(ts: str) -> float:
    """Convert timestamp string (HH:MM:SS.mmm) to seconds."""
    h, m, s = ts.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def seconds_to_timestamp(sec: float) -> str:
    """Convert seconds to timestamp string (HH:MM:SS.mmm)."""
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def parse_vtt(path: str) -> List[Segment]:
    """Parse VTT caption file into segments."""
    logger.info(f"Parsing VTT file: {path}")
    segs = []
    for i, cap in enumerate(webvtt.read(path)):
        start = time_to_seconds(cap.start)
        end = time_to_seconds(cap.end)
        text = clean_text(cap.text)
        if text.strip():
            segs.append(Segment(i, start, end, text))
    logger.info(f"Parsed {len(segs)} segments from VTT")
    return segs


def parse_srt(path: str) -> List[Segment]:
    """Parse SRT caption file into segments."""
    logger.info(f"Parsing SRT file: {path}")
    subs = pysrt.open(path)
    segs = []
    for i, s in enumerate(subs):
        start = (s.start.hours * 3600 + s.start.minutes * 60 + 
                s.start.seconds + s.start.milliseconds / 1000.0)
        end = (s.end.hours * 3600 + s.end.minutes * 60 + 
              s.end.seconds + s.end.milliseconds / 1000.0)
        text = clean_text(s.text)
        if text.strip():
            segs.append(Segment(i, start, end, text))
    logger.info(f"Parsed {len(segs)} segments from SRT")
    return segs


def load_segments(captions_path: str) -> List[Segment]:
    """Load segments from VTT or SRT caption file."""
    ext = os.path.splitext(captions_path)[1].lower()
    if ext == ".vtt":
        return parse_vtt(captions_path)
    elif ext == ".srt":
        return parse_srt(captions_path)
    else:
        raise ValueError("Captions must be .vtt or .srt")


def transcribe_audio(audio_path: str, out_path: str, 
                    model_size: str = None, device: str = None) -> List[Segment]:
    """
    Transcribe audio file using faster-whisper and save as VTT.
    Returns list of Segment objects.
    """
    model_size = model_size or Config.WHISPER_MODEL
    device = device or Config.WHISPER_DEVICE
    
    if device == "auto":
        device = "cpu"
    
    compute_type = "int8" if device == "cpu" else "float16"
    
    logger.info(f"Transcribing audio with Whisper (model={model_size}, device={device})")
    
    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    seg_iter, info = model.transcribe(
        audio_path,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=300),
    )
    
    logger.info(f"Detected language: {info.language} (probability: {info.language_probability:.2f})")
    
    segs: List[Segment] = []
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("WEBVTT\n\n")
        for i, s in enumerate(seg_iter):
            start, end = s.start, s.end
            text = clean_text(s.text)
            segs.append(Segment(i, start, end, text))
            f.write(f"{seconds_to_timestamp(start)} --> {seconds_to_timestamp(end)}\n{text}\n\n")
    
    logger.info(f"Transcription complete. Saved {len(segs)} segments to {out_path}")
    return segs
