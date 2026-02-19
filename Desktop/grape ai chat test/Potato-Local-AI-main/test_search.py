import time
from ddgs import DDGS
from ddgs.exceptions import RatelimitException, TimeoutException, DDGSException

print("=" * 50)
print("TEST 1: Basic DuckDuckGo search")
print("=" * 50)

start = time.time()
try:
    with DDGS(timeout=15) as ddgs:
        results = list(ddgs.text("future of space exploration", max_results=3))
    elapsed = time.time() - start
    print(f"Got {len(results)} results in {elapsed:.1f}s")
    for r in results:
        print(f"  - {r.get('title', '?')}")
except RatelimitException as e:
    print(f"RATE LIMITED after {time.time()-start:.1f}s: {e}")
except TimeoutException as e:
    print(f"TIMED OUT after {time.time()-start:.1f}s: {e}")
except Exception as e:
    print(f"ERROR after {time.time()-start:.1f}s: {type(e).__name__}: {e}")

print()
print("=" * 50)
print("TEST 2: Ollama connectivity")
print("=" * 50)

try:
    import ollama
    start = time.time()
    response = ollama.chat(
        model='qwen2.5:1.5b',
        messages=[{'role': 'user', 'content': 'Say hello in one word'}]
    )
    elapsed = time.time() - start
    print(f"Ollama responded in {elapsed:.1f}s: {response['message']['content']}")
except Exception as e:
    print(f"Ollama ERROR: {type(e).__name__}: {e}")

print()
print("=" * 50)
print("TEST 3: Full pipeline (like your app)")
print("=" * 50)

try:
    from ddgsearch import get_combined_response
    start = time.time()
    result = get_combined_response("is humanity destined for the stars")
    elapsed = time.time() - start
    print(f"Full response in {elapsed:.1f}s:")
    print(result[:500])
except Exception as e:
    print(f"Pipeline ERROR after {time.time()-start:.1f}s: {type(e).__name__}: {e}")
