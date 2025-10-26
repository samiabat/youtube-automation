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
    
    # API Keys
    PEXELS_API_KEY: Optional[str] = os.getenv("PEXELS_API_KEY")
    PIXABAY_API_KEY: Optional[str] = os.getenv("PIXABAY_API_KEY")
    
    # Whisper settings
    WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "small")
    WHISPER_DEVICE: str = os.getenv("WHISPER_DEVICE", "auto")
    
    # Video settings
    DEFAULT_RESOLUTION: str = os.getenv("DEFAULT_RESOLUTION", "1920x1080")
    DEFAULT_FPS: int = int(os.getenv("DEFAULT_FPS", "30"))
    DEFAULT_STYLE: str = os.getenv("DEFAULT_STYLE", "general")
    
    # Provider settings
    PRIMARY_PROVIDER: str = os.getenv("PRIMARY_PROVIDER", "pexels")
    FALLBACK_PROVIDER: str = os.getenv("FALLBACK_PROVIDER", "pixabay")
    
    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    
    @classmethod
    def validate(cls) -> bool:
        """Validate configuration. API keys are optional - will use fallback clips if not provided."""
        # API keys are now optional - return True always
        # If no API keys are provided, the system will use fallback gradient clips
        return True
    
    @classmethod
    def get_available_providers(cls) -> list:
        """Get list of available providers based on API keys."""
        providers = []
        if cls.PEXELS_API_KEY:
            providers.append("pexels")
        if cls.PIXABAY_API_KEY:
            providers.append("pixabay")
        return providers
