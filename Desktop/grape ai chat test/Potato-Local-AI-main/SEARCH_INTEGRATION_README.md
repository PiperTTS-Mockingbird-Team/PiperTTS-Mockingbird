# Multi-Source Search Integration

## Overview
Potato-Local-AI now uses a **multi-source search system** with automatic fallback support:

1. **Primary:** SearXNG (your local privacy-focused search server)
2. **Fallback 1:** DuckDuckGo
3. **Fallback 2:** Bing

## How It Works

The system automatically tries each source in order until it gets results:

```
User Query
    ↓
Try SearXNG (http://127.0.0.1:8888)
    ↓ (if fails or not running)
Try DuckDuckGo
    ↓ (if fails or rate limited)
Try Bing
    ↓
Return Results (or error if all fail)
```

## Configuration

### SearXNG Server Settings

Edit `multi_search.py` to change the SearXNG configuration:

```python
SEARXNG_URL = "http://127.0.0.1:8888"  # Change if your SearXNG runs on a different port
SEARXNG_TIMEOUT = 5  # seconds
```

### Common SearXNG URLs:
- Local default: `http://127.0.0.1:8888`
- Custom port: `http://127.0.0.1:YOUR_PORT`
- Remote server: `http://your-server-ip:8888`

## Testing

### Test the Search System
Run the test script to verify all search sources:
```bash
python multi_search.py
```

### Test Full Integration
```bash
python test_search.py
```

## Troubleshooting

### SearXNG Not Connecting?
1. **Is SearXNG running?**
   - Windows: Run `Start-SearXNG (Windows).bat` in your SearXNG folder
   - Check if http://127.0.0.1:8888 opens in your browser

2. **Check the port:**
   - SearXNG default is 8888
   - Verify in your SearXNG settings.yml file

3. **Firewall blocking?**
   - Make sure your firewall allows localhost connections

### Fallback Status Messages

When running searches, you'll see colored emoji indicators:

- 🔍 Trying SearXNG
- ✅ Successful search
- ❌ Connection failed (will fallback)
- ⚠️ Rate limit or error (will fallback)
- 🦆 Using DuckDuckGo fallback
- 🅱️ Using Bing fallback

## Benefits

### Why SearXNG First?
- **Privacy:** No tracking, no data collection
- **No Rate Limits:** Your own server = no API restrictions
- **Fast:** Local network speed
- **Customizable:** Configure which search engines SearXNG queries

### Why Fallbacks?
- **Reliability:** If SearXNG is offline, you still get results
- **Redundancy:** Multiple search sources ensure availability
- **Automatic:** No manual intervention needed

## Example Output

```
🔍 Trying SearXNG: 'Python programming tutorial'
✅ SearXNG returned 2 results
Source used: searxng

--- Result 1 ---
Title: Learn Python - Free Interactive Tutorial
URL: https://www.learnpython.org/
Snippet: Learn Python in the most social and fun way...
```

If SearXNG is offline:
```
🔍 Trying SearXNG: 'Python programming tutorial'
❌ SearXNG not available (connection failed)
🦆 Trying DuckDuckGo: 'Python programming tutorial'
✅ DuckDuckGo returned 2 results
Source used: duckduckgo
```

## Advanced Usage

### In Your Code

```python
from multi_search import search_multi_source

# Get detailed information about which source was used
results, source, errors = search_multi_source("your query", max_results=5)

print(f"Got {len(results)} results from {source}")
if errors:
    print(f"Encountered errors: {errors}")

for result in results:
    print(result['title'])
    print(result['href'])
    print(result['body'])
```

### Legacy Compatibility

The old `search_internet()` function still works for backwards compatibility:

```python
from multi_search import search_internet

results, error = search_internet("your query")
```

## Files Modified

- ✨ **NEW:** `multi_search.py` - Multi-source search engine
- 📝 **MODIFIED:** `ddgsearch.py` - Now imports from multi_search.py
- 📄 **NEW:** `SEARCH_INTEGRATION_README.md` - This file

## Requirements

All required packages are already in `requirements.txt`:
- `requests` (for SearXNG API calls)
- `duckduckgo-search` (for DDG and Bing fallbacks)

No additional installation needed! Your existing Python environment has everything.
