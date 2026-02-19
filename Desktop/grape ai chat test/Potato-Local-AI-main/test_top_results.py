"""
Test: Compare search speed with top 2 vs top 5 results per query.

This measures the total time for the full pipeline (search + LLM answer)
using max_results=2 and max_results=5 to see the performance difference.
"""

import time
import ollama
import concurrent.futures
from ddgs import DDGS
from ddgsearch import analyze_and_optimize_query, needs_internet_search
from datetime import datetime


def search_with_max(query, max_results):
    """Search DuckDuckGo with a specific max_results cap."""
    try:
        with DDGS(timeout=10) as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        return [r for r in results if 'body' in r]
    except Exception as e:
        print(f"  Search error: {e}")
        return []


def run_pipeline(user_query, max_results, label):
    """Run the full search+answer pipeline and return timing info."""
    print(f"\n{'='*60}")
    print(f"  [{label}] max_results={max_results}")
    print(f"{'='*60}")

    current_date = datetime.now().strftime("%A, %B %d, %Y")

    # Step 1: Optimize query
    t0 = time.perf_counter()
    search_queries = analyze_and_optimize_query(user_query)
    t_optimize = time.perf_counter() - t0
    print(f"  Optimized queries ({len(search_queries)}): {search_queries}")
    print(f"  Optimize time: {t_optimize:.2f}s")

    # Step 2: Concurrent searches
    t1 = time.perf_counter()
    all_results = []
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=len(search_queries))
    futures = {executor.submit(search_with_max, q, max_results): q for q in search_queries}
    try:
        for future in concurrent.futures.as_completed(futures, timeout=15):
            try:
                all_results.extend(future.result(timeout=10))
            except Exception:
                pass
    except concurrent.futures.TimeoutError:
        pass
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
    t_search = time.perf_counter() - t1
    print(f"  Results fetched: {len(all_results)}")
    print(f"  Search time: {t_search:.2f}s")

    # Step 3: Build context + generate answer
    if all_results:
        search_context = "\n".join([f"- {r.get('body')}" for r in all_results])
    else:
        search_context = "No results found."

    prompt = (
        f"Current Date: {current_date}\n\n"
        f"Search Results:\n{search_context}\n\n"
        f"Instructions: Use the Search Results and Current Date above to answer the question below. "
        "Be very direct. If the answer is in the text, use it. If not, give your best answer.\n\n"
        f"User Question: {user_query}\n\nAnswer:"
    )

    t2 = time.perf_counter()
    response = ollama.chat(
        model='qwen2.5:1.5b',
        messages=[{'role': 'user', 'content': prompt}]
    )
    t_llm = time.perf_counter() - t2
    answer = response['message']['content']
    print(f"  LLM time: {t_llm:.2f}s")
    print(f"  Answer preview: {answer[:120]}...")

    total = t_optimize + t_search + t_llm
    print(f"  TOTAL: {total:.2f}s")

    return {
        'max_results': max_results,
        'num_results': len(all_results),
        'optimize_time': t_optimize,
        'search_time': t_search,
        'llm_time': t_llm,
        'total_time': total,
        'prompt_len': len(prompt),
    }


if __name__ == "__main__":
    test_query = "gemma is a local ai model google releases every so often when will gemma 4 come out"

    print("=" * 60)
    print("  BENCHMARK: top 2 vs top 5 results per search query")
    print(f"  Query: \"{test_query}\"")
    print("=" * 60)

    # Run top-5 first, then top-2
    stats_5 = run_pipeline(test_query, max_results=5, label="TOP 5")
    stats_2 = run_pipeline(test_query, max_results=2, label="TOP 2")

    # Summary
    print("\n")
    print("=" * 60)
    print("  RESULTS SUMMARY")
    print("=" * 60)
    print(f"  {'Metric':<25} {'Top 5':>10} {'Top 2':>10} {'Diff':>10}")
    print(f"  {'-'*55}")
    print(f"  {'Results fetched':<25} {stats_5['num_results']:>10} {stats_2['num_results']:>10} {stats_2['num_results'] - stats_5['num_results']:>+10}")
    print(f"  {'Search time (s)':<25} {stats_5['search_time']:>10.2f} {stats_2['search_time']:>10.2f} {stats_2['search_time'] - stats_5['search_time']:>+10.2f}")
    print(f"  {'LLM time (s)':<25} {stats_5['llm_time']:>10.2f} {stats_2['llm_time']:>10.2f} {stats_2['llm_time'] - stats_5['llm_time']:>+10.2f}")
    print(f"  {'Total time (s)':<25} {stats_5['total_time']:>10.2f} {stats_2['total_time']:>10.2f} {stats_2['total_time'] - stats_5['total_time']:>+10.2f}")
    print(f"  {'Prompt length (chars)':<25} {stats_5['prompt_len']:>10} {stats_2['prompt_len']:>10} {stats_2['prompt_len'] - stats_5['prompt_len']:>+10}")
    
    speedup = stats_5['total_time'] - stats_2['total_time']
    pct = (speedup / stats_5['total_time']) * 100 if stats_5['total_time'] > 0 else 0
    print(f"\n  Top 2 is {abs(speedup):.2f}s {'faster' if speedup > 0 else 'slower'} ({abs(pct):.1f}%)")
    print()
