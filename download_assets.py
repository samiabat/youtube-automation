"""
Stock video/image download module.
Handles fetching assets from Pexels and Pixabay providers.
Also provides background music downloading capability.
"""
import os
import logging
from typing import List, Optional, Tuple
import requests

from config import Config

logger = logging.getLogger(__name__)

# Minimum file size to consider valid (10KB)
MIN_VALID_FILE_SIZE = 10000


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


def fetch_asset_url(query: str, primary: Optional[StockProvider], 
                   fallback: Optional[StockProvider],
                   image_fallback: Optional[ImageFallbackProvider] = None,
                   used_urls: Optional[set] = None) -> Tuple[Optional[str], str]:
    """
    Fetch a video or image URL for the given query.
    Returns (url, asset_type) where asset_type is 'video' or 'image'.
    
    Args:
        query: Search query string
        primary: Primary video provider
        fallback: Fallback video provider
        image_fallback: Image fallback provider
        used_urls: Set of already used URLs to avoid repetition
    """
    if used_urls is None:
        used_urls = set()
    
    # Increase count to get more variety
    search_count = 10
    
    # Combine results from both providers for more variety
    all_video_urls = []
    
    # Try primary video provider
    if primary:
        try:
            urls = primary.search(query, count=search_count)
            if urls:
                logger.info(f"Primary provider returned {len(urls)} videos for query: '{query}'")
                all_video_urls.extend([(url, "primary") for url in urls])
        except Exception as e:
            logger.warning(f"Primary provider failed for '{query}': {e}")
    
    # Try fallback video provider
    if fallback:
        try:
            urls = fallback.search(query, count=search_count)
            if urls:
                logger.info(f"Fallback provider returned {len(urls)} videos for query: '{query}'")
                all_video_urls.extend([(url, "fallback") for url in urls])
        except Exception as e:
            logger.warning(f"Fallback provider failed for '{query}': {e}")
    
    # Filter out already used URLs and select randomly from remaining
    if all_video_urls:
        import random
        unused_urls = [(url, source) for url, source in all_video_urls if url not in used_urls]
        
        if unused_urls:
            selected_url, source = random.choice(unused_urls)
            used_urls.add(selected_url)
            logger.info(f"Selected unused video from {source} provider (total available: {len(all_video_urls)}, unused: {len(unused_urls)})")
            return selected_url, "video"
        else:
            # All URLs have been used, pick randomly from all
            selected_url, source = random.choice(all_video_urls)
            used_urls.add(selected_url)
            logger.warning(f"All videos have been used before, reusing from {source} provider")
            return selected_url, "video"
    
    # Try image fallback
    if image_fallback:
        try:
            urls = image_fallback.search(query, count=search_count)
            if urls:
                # Filter out used image URLs
                unused_urls = [url for url in urls if url not in used_urls]
                if unused_urls:
                    import random
                    selected_url = random.choice(unused_urls)
                    used_urls.add(selected_url)
                    logger.info(f"Selected unused image from fallback (total: {len(urls)}, unused: {len(unused_urls)})")
                    return selected_url, "image"
                else:
                    # All used, pick randomly anyway
                    import random
                    selected_url = random.choice(urls)
                    used_urls.add(selected_url)
                    logger.warning("All images have been used before, reusing")
                    return selected_url, "image"
        except Exception as e:
            logger.warning(f"Image fallback failed for '{query}': {e}")
    
    logger.warning(f"No assets found for query: '{query}'")
    return None, "none"


def download_background_music(tmpdir: str, duration: float) -> Optional[str]:
    """
    Download a free background music track suitable for storytelling.
    Uses Pixabay Music API or free music archives.
    
    Args:
        tmpdir: Temporary directory for downloads
        duration: Target duration in seconds (to select appropriate length track)
    
    Returns:
        Path to downloaded music file, or None if download fails
    """
    # List of free background music URLs (royalty-free, no attribution required)
    # These are from Free Music Archive and other CC0 sources
    free_music_urls = [
        # Classical/Ambient tracks (royalty-free, suitable for background)
        "https://cdn.pixabay.com/download/audio/2022/03/10/audio_d1718ab41b.mp3",  # Classical Piano
        "https://cdn.pixabay.com/download/audio/2022/05/27/audio_1808fbf07a.mp3",  # Ambient Calm
        "https://cdn.pixabay.com/download/audio/2021/08/04/audio_0625c1539c.mp3",  # Soft Piano
        "https://cdn.pixabay.com/download/audio/2022/03/24/audio_4019b9d915.mp3",  # Peaceful Ambient
    ]
    
    try:
        import random
        # Select a random track to avoid repetition across videos
        music_url = random.choice(free_music_urls)
        
        os.makedirs(tmpdir, exist_ok=True)
        music_path = os.path.join(tmpdir, "background_music.mp3")
        
        # Check if already downloaded
        if os.path.exists(music_path) and os.path.getsize(music_path) > 10000:
            logger.info(f"Background music already downloaded: {music_path}")
            return music_path
        
        logger.info(f"Downloading background music from: {music_url}")
        with requests.get(music_url, stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(music_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1 << 20):
                    if chunk:
                        f.write(chunk)
        
        # Validate downloaded file
        if os.path.getsize(music_path) < 10000:
            logger.error("Downloaded music file is too small, removing")
            os.remove(music_path)
            return None
        
        logger.info(f"Background music downloaded successfully: {music_path}")
        return music_path
        
    except Exception as e:
        logger.error(f"Failed to download background music: {e}")
        return None
