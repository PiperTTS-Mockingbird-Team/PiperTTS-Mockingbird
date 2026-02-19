"""
Multi-source search module with SearXNG integration and fallbacks to DuckDuckGo and Bing.
Priority: SearXNG -> DuckDuckGo -> Bing
"""
import requests
from ddgs import DDGS
from ddgs.exceptions import RatelimitException, TimeoutException, DDGSException

# Configuration
SEARXNG_URL = "http://127.0.0.1:8888"
SEARXNG_TIMEOUT = 5  # seconds

def search_searxng(query, max_results=2):
    """
    Search using local SearXNG instance.
    Returns tuple: (results_list, error_type)
    error_type is None on success, or 'connection'/'timeout'/'error' on failure.
    """
    try:
        print(f"🔍 Trying SearXNG: '{query}'")
        params = {
            'q': query,
            'format': 'json',
            'language': 'en',
            'safesearch': 0,
            'categories': 'general'
        }
        
        response = requests.get(
            f"{SEARXNG_URL}/search",
            params=params,
            timeout=SEARXNG_TIMEOUT
        )
        
        if response.status_code == 200:
            data = response.json()
            results = []

            # Filter first (body must exist), then cap at max_results.
            # This mirrors how DDG/Bing handle it and ensures we don't get
            # fewer results than requested just because some items lack content.
            for item in data.get('results', []):
                result = {
                    'title': item.get('title', ''),
                    'href': item.get('url', ''),
                    'body': item.get('content', '')
                }
                if result['body']:  # Only include if it has content
                    results.append(result)
                if len(results) >= max_results:
                    break
            
            print(f"✅ SearXNG returned {len(results)} results")
            return results, None
        else:
            print(f"⚠️ SearXNG returned status code {response.status_code}")
            return [], 'error'
            
    except requests.exceptions.ConnectionError:
        print("❌ SearXNG not available (connection failed)")
        return [], 'connection'
    except requests.exceptions.Timeout:
        print("⏱️ SearXNG timed out")
        return [], 'timeout'
    except Exception as e:
        print(f"❌ SearXNG error: {e}")
        return [], 'error'

def search_duckduckgo(query, max_results=2):
    """
    Search using DuckDuckGo.
    Returns tuple: (results_list, error_type)
    error_type is None on success, or 'ratelimit'/'timeout'/'error' on failure.
    """
    try:
        print(f"🦆 Trying DuckDuckGo: '{query}'")
        with DDGS(timeout=10) as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        
        filtered = [result for result in results if 'body' in result]
        print(f"✅ DuckDuckGo returned {len(filtered)} results")
        return filtered, None
        
    except RatelimitException as e:
        print(f"⚠️ DuckDuckGo rate limited: {e}")
        return [], 'ratelimit'
    except TimeoutException as e:
        print(f"⏱️ DuckDuckGo timed out: {e}")
        return [], 'timeout'
    except DDGSException as e:
        print(f"❌ DuckDuckGo error: {e}")
        return [], 'error'
    except Exception as e:
        print(f"❌ Unexpected DuckDuckGo error: {e}")
        return [], 'error'

def search_bing(query, max_results=2):
    """
    Search using Bing (via DuckDuckGo's Bing support).
    Returns tuple: (results_list, error_type)
    error_type is None on success, or 'ratelimit'/'timeout'/'error' on failure.
    """
    try:
        print(f"🅱️ Trying Bing fallback: '{query}'")
        # Using DDGS which can also query Bing-like results
        # Note: This is a simplified Bing fallback - you could use official Bing API if you have a key
        with DDGS(timeout=10) as ddgs:
            results = list(ddgs.text(query, max_results=max_results, backend='lite'))
        
        filtered = [result for result in results if 'body' in result]
        print(f"✅ Bing fallback returned {len(filtered)} results")
        return filtered, None
        
    except RatelimitException as e:
        print(f"⚠️ Bing fallback rate limited: {e}")
        return [], 'ratelimit'
    except TimeoutException as e:
        print(f"⏱️ Bing fallback timed out: {e}")
        return [], 'timeout'
    except Exception as e:
        print(f"❌ Bing fallback error: {e}")
        return [], 'error'

def search_multi_source(query, max_results=2):
    """
    Performs search with priority: SearXNG -> DuckDuckGo -> Bing.
    Always tries to get results from at least one source.
    
    Returns tuple: (results_list, source_used, errors_encountered)
    - results_list: List of search results
    - source_used: String indicating which source succeeded ('searxng', 'duckduckgo', 'bing', or 'none')
    - errors_encountered: Set of error types encountered
    """
    all_errors = set()
    
    # Try SearXNG first
    results, error = search_searxng(query, max_results)
    if results:
        return results, 'searxng', all_errors
    if error:
        all_errors.add(f'searxng_{error}')
    
    # Fallback to DuckDuckGo
    results, error = search_duckduckgo(query, max_results)
    if results:
        return results, 'duckduckgo', all_errors
    if error:
        all_errors.add(f'ddg_{error}')
    
    # Final fallback to Bing
    results, error = search_bing(query, max_results)
    if results:
        return results, 'bing', all_errors
    if error:
        all_errors.add(f'bing_{error}')
    
    # If all failed
    print("❌ All search sources failed")
    return [], 'none', all_errors

# For backwards compatibility with existing code
def search_internet(query, max_results=2):
    """
    Legacy compatibility function that matches the original ddgsearch.py interface.
    Returns tuple: (results_list, error_type)
    """
    results, source, errors = search_multi_source(query, max_results=max_results)
    
    if results:
        return results, None
    else:
        # Return the most relevant error type
        if any('ratelimit' in e for e in errors):
            return [], 'ratelimit'
        elif any('timeout' in e for e in errors):
            return [], 'timeout'
        else:
            return [], 'error'

if __name__ == "__main__":
    # Test the search
    print("\n" + "="*60)
    print("Testing Multi-Source Search")
    print("="*60 + "\n")
    
    test_query = "Python programming tutorial"
    results, source, errors = search_multi_source(test_query)
    
    print(f"\n{'='*60}")
    print(f"Source used: {source}")
    print(f"Errors encountered: {errors if errors else 'None'}")
    print(f"Results found: {len(results)}")
    print(f"{'='*60}\n")
    
    for i, result in enumerate(results, 1):
        print(f"\n--- Result {i} ---")
        print(f"Title: {result.get('title', 'N/A')}")
        print(f"URL: {result.get('href', 'N/A')}")
        print(f"Snippet: {result.get('body', 'N/A')[:150]}...")
