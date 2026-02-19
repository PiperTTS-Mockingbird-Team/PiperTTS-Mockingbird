from PIL import Image, ImageTk, ImageDraw
import requests
from io import BytesIO
import re
from urllib.parse import urlparse
import ollama

IMAGE_MODEL = 'qwen3:1.7b'

# Mirroring the debugged format from ddgsearch.py
IMAGE_SYSTEM_MSG = """You suggest visual search terms. Always reply using ONLY this format:

SEARCH: first visual subject
SEARCH: second visual subject

Keep keywords short and search-friendly. Reply with ONLY SEARCH: lines. Max 2 lines."""

def get_image_keywords(user_query, ai_response):
    """Uses LLM to suggest 1-2 visual search terms based on the debugged SEARCH: format."""
    try:
        response = ollama.chat(
            model=IMAGE_MODEL,
            messages=[
                {'role': 'system', 'content': IMAGE_SYSTEM_MSG},
                {'role': 'user', 'content': f"User: {user_query}\nAI: {ai_response}"}
            ]
        )
        content = response['message']['content'].strip()
        
        # Using the same parsing logic that has already been debugged in ddgsearch.py
        search_terms = []
        for line in content.split('\n'):
            line = line.strip()
            if line.upper().startswith('SEARCH:'):
                term = line[7:].strip()
                if term:
                    search_terms.append(term)
            if len(search_terms) >= 2:
                break
        return search_terms
    except Exception as e:
        print(f"Error suggesting image keywords: {e}")
        return []

BING_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# Minimum pixel dimension (width AND height) to accept a downloaded image
MIN_IMG_DIMENSION = 80

# Domains that are always skipped (spam, clickbait, low-quality aggregators)
BLOCKED_IMAGE_DOMAINS = {
    'pinterest.com', 'pinterest.co.uk', 'pinterest.fr',
    'tumblr.com',
    'imgflip.com', 'meme-arsenal.com', 'memedroid.com',
    'alamy.com', 'shutterstock.com', 'gettyimages.com',
    'dreamstime.com', 'depositphotos.com', 'istockphoto.com',
    'teespring.com', 'redbubble.com', 'teepublic.com',
}

# Trusted domains — images from these are sorted to the front of results
TRUSTED_IMAGE_DOMAINS = {
    'wikipedia.org', 'wikimedia.org', 'upload.wikimedia.org',
    'nasa.gov', 'noaa.gov', 'usgs.gov',
    'nationalgeographic.com', 'nature.com', 'scientificamerican.com',
    'bbc.com', 'bbc.co.uk', 'reuters.com', 'apnews.com',
    'britannica.com', 'smithsonianmag.com',
    'history.com', 'si.edu', 'loc.gov',
    'github.com', 'githubusercontent.com',
}


def _domain_of(url: str) -> str:
    """Return the registered domain (e.g. 'wikipedia.org') from a URL."""
    try:
        host = urlparse(url).netloc.lower().lstrip('www.')
        return host
    except Exception:
        return ''


def _is_blocked(url: str) -> bool:
    domain = _domain_of(url)
    return any(domain == b or domain.endswith('.' + b) for b in BLOCKED_IMAGE_DOMAINS)


def _is_trusted(url: str) -> bool:
    domain = _domain_of(url)
    return any(domain == t or domain.endswith('.' + t) for t in TRUSTED_IMAGE_DOMAINS)


def fetch_images_for_keywords(keywords, candidates_per_keyword=12):
    """Fetches image URLs for multiple keywords using Bing Image Search.
    Returns dict of {keyword: [url, url, ...]}
    """
    results = {}
    for kw in keywords:
        try:
            url = (
                f'https://www.bing.com/images/search?q={requests.utils.quote(kw)}'
                f'&first=1&count={candidates_per_keyword}&safeSearch=Moderate'
            )
            r = requests.get(url, headers=BING_HEADERS, timeout=10)
            r.raise_for_status()
            # Extract media URLs from Bing's HTML
            raw_urls = re.findall(r'murl&quot;:&quot;(https?://[^&]+?)&quot;', r.text)
            # 1. Remove blocked domains
            raw_urls = [u for u in raw_urls if not _is_blocked(u)]
            # 2. Deduplicate: keep only the first URL per unique (domain + path) pair
            seen_keys = set()
            deduped = []
            for u in raw_urls:
                try:
                    parsed = urlparse(u)
                    key = f"{parsed.netloc}{parsed.path.rstrip('/')}"
                    if key not in seen_keys:
                        seen_keys.add(key)
                        deduped.append(u)
                except Exception:
                    deduped.append(u)
            # 3. Sort: trusted domains first, everything else after
            deduped.sort(key=lambda u: (0 if _is_trusted(u) else 1))
            results[kw] = deduped[:candidates_per_keyword]
            print(f"Bing: Found {len(results[kw])} image candidates for '{kw}' (filtered/sorted)")
        except Exception as e:
            print(f"Bing image search failed for '{kw}': {e}")
            results[kw] = []
    return results

def download_and_process_image(url, max_size=(180, 140), lightbox_size=(800, 600)):
    """Downloads an image once, returns (thumbnail, lightbox_img) or None on failure."""
    try:
        response = requests.get(url, timeout=7, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        response.raise_for_status()
        img_data = BytesIO(response.content)
        img = Image.open(img_data)

        # Reject images that are too small to be useful (icons, tracking pixels, etc.)
        if img.width < MIN_IMG_DIMENSION or img.height < MIN_IMG_DIMENSION:
            print(f"Skipping small image ({img.width}x{img.height}): {url}")
            return None

        # Convert to RGB
        if img.mode != "RGB":
            img = img.convert("RGB")

        # Lightbox version — larger copy from the same download
        lightbox = img.copy()
        lightbox.thumbnail(lightbox_size, Image.Resampling.LANCZOS)

        # Thumbnail version for the strip
        img.thumbnail(max_size, Image.Resampling.LANCZOS)

        # Add a subtle dark border (2px) to thumbnail only
        border = 2
        bordered = Image.new("RGB", (img.width + border * 2, img.height + border * 2), "#555555")
        bordered.paste(img, (border, border))

        return bordered, lightbox
    except Exception as e:
        print(f"Failed to download/process {url}: {e}")
        return None
