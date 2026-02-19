import time
import ollama
from ddgsearch import needs_internet_search, analyze_and_optimize_query, perform_concurrent_searches

query = "is humanity destined for the stars"

print("Step 1: needs_internet_search...")
start = time.time()
do_search = needs_internet_search(query)
print(f"  Result: {do_search} ({time.time()-start:.1f}s)")

if do_search:
    print("Step 2: analyze_and_optimize_query...")
    start = time.time()
    search_queries = analyze_and_optimize_query(query)
    print(f"  Queries: {search_queries} ({time.time()-start:.1f}s)")

    print("Step 3: perform_concurrent_searches...")
    start = time.time()
    results, errors = perform_concurrent_searches(search_queries)
    print(f"  Results: {len(results)}, Errors: {errors} ({time.time()-start:.1f}s)")

    print("Step 4: Ollama final response...")
    start = time.time()
    
    if results:
        search_context = "\n".join([f"- {r.get('body')}" for r in results])
    else:
        search_context = "No results found."
    
    prompt = f"Search Results:\n{search_context}\n\nUser Question: {query}\n\nAnswer briefly:"
    
    try:
        response = ollama.chat(
            model='qwen2.5:1.5b',
            messages=[{'role': 'user', 'content': prompt}]
        )
        print(f"  Response ({time.time()-start:.1f}s): {response['message']['content'][:200]}")
    except Exception as e:
        print(f"  ERROR ({time.time()-start:.1f}s): {e}")
else:
    print("No search needed, going directly to Ollama...")
    start = time.time()
    response = ollama.chat(
        model='qwen2.5:1.5b',
        messages=[{'role': 'user', 'content': query}]
    )
    print(f"  Response ({time.time()-start:.1f}s): {response['message']['content'][:200]}")

print("\nDone!")
