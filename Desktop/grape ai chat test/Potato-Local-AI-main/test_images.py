"""Quick diagnostic to see what's failing with image search."""
import sys, os
os.environ['no_proxy'] = '*'
os.environ['http_proxy'] = ''
os.environ['https_proxy'] = ''

from ddgs import DDGS
import requests
from io import BytesIO
from PIL import Image

keywords = ["Naruto Uzumaki", "Hidden Leaf Village"]

print("=== Step 1: Fetching image URLs ===", flush=True)
try:
    with DDGS() as ddgs:
        for kw in keywords:
            print(f"\nSearching images for: '{kw}'", flush=True)
            try:
                results = list(ddgs.images(kw, max_results=5))
                urls = [r['image'] for r in results if 'image' in r]
                print(f"  Got {len(urls)} URLs", flush=True)
                for i, url in enumerate(urls):
                    print(f"  [{i}] {url[:80]}...", flush=True)
            except Exception as e:
                print(f"  FAILED: {e}", flush=True)
            
            import time
            time.sleep(1)
except Exception as e:
    print(f"Session error: {e}", flush=True)

print("\n=== Step 2: Testing downloads ===", flush=True)
# Test downloading the first URL from each keyword
try:
    with DDGS() as ddgs:
        results = list(ddgs.images("Naruto Uzumaki", max_results=3))
        urls = [r['image'] for r in results if 'image' in r]
        
        for url in urls[:3]:
            print(f"\nDownloading: {url[:60]}...", flush=True)
            try:
                r = requests.get(url, timeout=7, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                })
                print(f"  Status: {r.status_code}, Size: {len(r.content)} bytes", flush=True)
                img = Image.open(BytesIO(r.content))
                print(f"  Image mode: {img.mode}, Size: {img.size}", flush=True)
                img = img.convert("RGB")
                img.thumbnail((200, 200))
                print(f"  SUCCESS - Resized to: {img.size}", flush=True)
            except Exception as e:
                print(f"  DOWNLOAD FAILED: {e}", flush=True)
except Exception as e:
    print(f"Test error: {e}", flush=True)

print("\nDone!", flush=True)
