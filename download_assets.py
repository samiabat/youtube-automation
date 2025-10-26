"""
Asset download module.
Handles downloading and validating media assets.
"""
import os
import logging
from typing import Optional, Tuple
import requests

from config import Config

logger = logging.getLogger(__name__)

# Minimum file size to consider valid (10KB)
MIN_VALID_FILE_SIZE = 10000


def validate_asset(path: str) -> bool:
    """
    Validate that a downloaded asset is usable.
    Checks file size to ensure it's not empty or corrupted.
    
    Args:
        path: Path to the asset file
        
    Returns:
        True if asset is valid, False otherwise
    """
    if not os.path.exists(path):
        logger.warning(f"Asset file does not exist: {path}")
        return False
    
    file_size = os.path.getsize(path)
    if file_size < MIN_VALID_FILE_SIZE:
        logger.warning(f"Asset file is too small ({file_size} bytes): {path}")
        return False
    
    logger.debug(f"Asset validated: {path} ({file_size} bytes)")
    return True


def download_asset(url: str, tmpdir: str) -> str:
    """Download a video or image file to temporary directory."""
    os.makedirs(tmpdir, exist_ok=True)
    
    # Determine file extension from URL or use .mp4 as default
    ext = ".mp4"
    if any(img_ext in url.lower() for img_ext in [".jpg", ".jpeg", ".png"]):
        ext = ".jpg"
    
    fn = os.path.join(tmpdir, f"asset_{abs(hash(url))}{ext}")
    
    if os.path.exists(fn):
        logger.debug(f"Asset already downloaded: {fn}")
        # Validate existing file
        if validate_asset(fn):
            return fn
        else:
            logger.warning(f"Existing asset is invalid, re-downloading: {fn}")
            os.remove(fn)
    
    try:
        logger.info(f"Downloading asset from: {url}")
        with requests.get(url, stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(fn, "wb") as f:
                for chunk in r.iter_content(chunk_size=1 << 20):
                    if chunk:
                        f.write(chunk)
        
        # Validate downloaded file
        if not validate_asset(fn):
            logger.error(f"Downloaded asset is invalid (too small or empty): {fn}")
            if os.path.exists(fn):
                os.remove(fn)
            raise ValueError(f"Downloaded asset from {url} is invalid")
        
        logger.info(f"Downloaded and validated asset: {fn}")
        return fn
    except Exception as e:
        logger.error(f"Failed to download asset from {url}: {e}")
        raise
