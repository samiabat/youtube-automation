"""
Stock video/image download module.
Handles fetching assets from Pexels and Pixabay providers.
"""
import os
import logging
from typing import List, Optional
import requests

from config import Config

logger = logging.getLogger(__name__)


class StockProvider:
    """Base class for stock media providers."""
    
    def search(self, query: str, count: int = 3, orientation: Optional[str] = None, 
               resolution: Optional[str] = None) -> List[str]:
        raise NotImplementedError


class PexelsProvider(StockProvider):
    """Pexels video provider."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.key = api_key or Config.PEXELS_API_KEY
        self.base = "https://api.pexels.com/videos/search"
        if not self.key:
            raise ValueError("PEXELS_API_KEY not set")
    
    def search(self, query: str, count: int = 3, orientation: Optional[str] = None, 
               resolution: Optional[str] = None) -> List[str]:
        """Search for videos on Pexels."""
        headers = {"Authorization": self.key}
        params = {"query": query, "per_page": count}
        
        try:
            logger.info(f"Searching Pexels for: '{query}'")
            r = requests.get(self.base, headers=headers, params=params, timeout=30)
            r.raise_for_status()
            data = r.json()
            urls = []
            
            for v in data.get("videos", []):
                files = v.get("video_files", [])
                files = sorted(files, key=lambda f: abs((f.get("height") or 0) - 1080))
                if files:
                    urls.append(files[0]["link"])
            
            logger.info(f"Pexels returned {len(urls)} video URLs for query '{query}'")
            return urls
        except Exception as e:
            logger.error(f"Pexels search failed for '{query}': {e}")
            return []


class PixabayProvider(StockProvider):
    """Pixabay video provider."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.key = api_key or Config.PIXABAY_API_KEY
        self.base = "https://pixabay.com/api/videos/"
        if not self.key:
            raise ValueError("PIXABAY_API_KEY not set")
    
    def search(self, query: str, count: int = 3, orientation: Optional[str] = None, 
               resolution: Optional[str] = None) -> List[str]:
        """Search for videos on Pixabay."""
        params = {"key": self.key, "q": query, "per_page": count}
        
        try:
            logger.info(f"Searching Pixabay for: '{query}'")
            r = requests.get(self.base, params=params, timeout=30)
            r.raise_for_status()
            data = r.json()
            urls = []
            
            for hit in data.get("hits", []):
                vids = hit.get("videos", {})
                for k in ["large", "full_hd", "hd", "medium"]:
                    if k in vids and vids[k].get("url"):
                        urls.append(vids[k]["url"])
                        break
            
            logger.info(f"Pixabay returned {len(urls)} video URLs for query '{query}'")
            return urls
        except Exception as e:
            logger.error(f"Pixabay search failed for '{query}': {e}")
            return []


class ImageFallbackProvider:
    """Fallback provider that uses static images from Pexels/Pixabay photo APIs."""
    
    def __init__(self, api_key: Optional[str] = None, provider_type: str = "pexels"):
        self.provider_type = provider_type
        if provider_type == "pexels":
            self.key = api_key or Config.PEXELS_API_KEY
            self.base = "https://api.pexels.com/v1/search"
        elif provider_type == "pixabay":
            self.key = api_key or Config.PIXABAY_API_KEY
            self.base = "https://pixabay.com/api/"
        else:
            raise ValueError(f"Unknown provider type: {provider_type}")
        
        if not self.key:
            raise ValueError(f"{provider_type.upper()}_API_KEY not set")
    
    def search(self, query: str, count: int = 3) -> List[str]:
        """Search for images."""
        try:
            logger.info(f"Searching {self.provider_type} images for: '{query}'")
            
            if self.provider_type == "pexels":
                headers = {"Authorization": self.key}
                params = {"query": query, "per_page": count}
                r = requests.get(self.base, headers=headers, params=params, timeout=30)
                r.raise_for_status()
                data = r.json()
                urls = [photo.get("src", {}).get("large2x") or photo.get("src", {}).get("large") 
                       for photo in data.get("photos", [])]
            else:  # pixabay
                params = {"key": self.key, "q": query, "per_page": count, "image_type": "photo"}
                r = requests.get(self.base, params=params, timeout=30)
                r.raise_for_status()
                data = r.json()
                urls = [hit.get("largeImageURL") for hit in data.get("hits", [])]
            
            urls = [u for u in urls if u]  # Filter out None values
            logger.info(f"{self.provider_type} returned {len(urls)} image URLs for query '{query}'")
            return urls
        except Exception as e:
            logger.error(f"{self.provider_type} image search failed for '{query}': {e}")
            return []


def make_provider(name: Optional[str]) -> Optional[StockProvider]:
    """Factory function to create a provider instance."""
    if not name:
        return None
    
    if name == "pexels" and Config.PEXELS_API_KEY:
        return PexelsProvider()
    if name == "pixabay" and Config.PIXABAY_API_KEY:
        return PixabayProvider()
    
    logger.warning(f"Provider '{name}' not available (API key missing)")
    return None


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
        return fn
    
    try:
        logger.info(f"Downloading asset from: {url}")
        with requests.get(url, stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(fn, "wb") as f:
                for chunk in r.iter_content(chunk_size=1 << 20):
                    if chunk:
                        f.write(chunk)
        logger.info(f"Downloaded asset to: {fn}")
        return fn
    except Exception as e:
        logger.error(f"Failed to download asset from {url}: {e}")
        raise


def fetch_asset_url(query: str, primary: Optional[StockProvider], 
                   fallback: Optional[StockProvider],
                   image_fallback: Optional[ImageFallbackProvider] = None) -> tuple[Optional[str], str]:
    """
    Fetch a video or image URL for the given query.
    Returns (url, asset_type) where asset_type is 'video' or 'image'.
    """
    # Try primary video provider
    if primary:
        try:
            urls = primary.search(query, count=3)
            if urls:
                logger.info(f"Using video from primary provider for query: '{query}'")
                return urls[0], "video"
        except Exception as e:
            logger.warning(f"Primary provider failed for '{query}': {e}")
    
    # Try fallback video provider
    if fallback:
        try:
            urls = fallback.search(query, count=3)
            if urls:
                logger.info(f"Using video from fallback provider for query: '{query}'")
                return urls[0], "video"
        except Exception as e:
            logger.warning(f"Fallback provider failed for '{query}': {e}")
    
    # Try image fallback
    if image_fallback:
        try:
            urls = image_fallback.search(query, count=3)
            if urls:
                logger.info(f"Using image fallback for query: '{query}'")
                return urls[0], "image"
        except Exception as e:
            logger.warning(f"Image fallback failed for '{query}': {e}")
    
    logger.warning(f"No assets found for query: '{query}'")
    return None, "none"
