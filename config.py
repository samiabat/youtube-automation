"""
Configuration loader for YouTube automation.
Loads API keys and settings from .env file.
"""
import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Configuration class that loads settings from environment variables."""
    
    # Whisper settings
    WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "small")
    WHISPER_DEVICE: str = os.getenv("WHISPER_DEVICE", "auto")
    
    # Video settings
    DEFAULT_RESOLUTION: str = os.getenv("DEFAULT_RESOLUTION", "1920x1080")
    DEFAULT_FPS: int = int(os.getenv("DEFAULT_FPS", "30"))
    DEFAULT_STYLE: str = os.getenv("DEFAULT_STYLE", "general")
    
    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
