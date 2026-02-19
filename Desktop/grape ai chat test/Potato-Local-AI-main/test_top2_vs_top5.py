"""
Benchmark: top 2 results per search vs top 5 results per search.
Skips the optimizer LLM step — uses fixed search queries so we can
purely compare search speed + answer generation speed.
"""
import sys
import os
import time
import requests
import concurrent.futures
from ddgs import DDGS
from datetime import datetime

# Force UTF-8 encoding for Windows terminals
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Disable output buffering for real-time logs
sys.stdout.reconfigure(line_buffering=True)

MODEL = 'qwen2.5:1.5b'

# ── helpers ──────────────────────────────────────────────────────────

import ollama

def ollama_chat(model, messages):
    """Call Ollama via official library."""
    response = ollama.chat(model=model, messages=messages)
    return response['message']['content']


def search_ddg(query, max_results=5):
    """Search DuckDuckGo."""
    try:
        with DDGS(timeout=10) as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        return [r for r in results if 'body' in r]
    except Exception as e:
        print(f"  search error: {e}")
        return []


def concurrent_search(queries, max_results=5):
    """Run searches sequentially for better stability in this environment."""
    all_results = []
    for q in queries:
        try:
            print(f"  Searching: {q}...", flush=True)
            all_results.extend(search_ddg(q, max_results=max_results))
        except Exception as e:
            print(f"  Error: {e}", flush=True)
    return all_results


# ── benchmark one run ────────────────────────────────────────────────

def run_test(search_queries, max_results, user_query):
    """Search with given max_results, then generate answer. Returns timings dict."""
    label = f"top {max_results}"
    print(f"\n{'='*60}", flush=True)
    print(f"  Testing: {label}  ({max_results} results per search x {len(search_queries)} searches)", flush=True)
    print(f"{'='*60}", flush=True)

    # 1. Search
    t0 = time.perf_counter()
    results = concurrent_search(search_queries, max_results=max_results)
    t_search = time.perf_counter() - t0
    print(f"  Search: {t_search:.2f}s  ->  {len(results)} results", flush=True)

    # 2. Build prompt & answer
    context = "\n".join(f"- {r.get('body','')}" for r in results)
    current_date = datetime.now().strftime("%A, %B %d, %Y")
    prompt = (
        f"Current Date: {current_date}\n\n"
        f"Search Results:\n{context}\n\n"
        f"Use the search results to answer the question. Be direct.\n\n"
        f"Question: {user_query}\n\nAnswer:"
    )
    prompt_chars = len(prompt)
    print(f"  Prompt size: {prompt_chars} chars", flush=True)

    t0 = time.perf_counter()
    answer = ollama_chat(MODEL, [{'role': 'user', 'content': prompt}])
    t_answer = time.perf_counter() - t0
    print(f"  Answer: {t_answer:.2f}s", flush=True)
    print(f"  Preview: {answer[:150].strip()}...", flush=True)

    total = t_search + t_answer
    print(f"  TOTAL: {total:.2f}s", flush=True)
    return {
        'max_results': max_results,
        'num_results': len(results),
        'prompt_chars': prompt_chars,
        't_search': t_search,
        't_answer': t_answer,
        't_total': total,
        'answer': answer,
    }


# ── main ─────────────────────────────────────────────────────────────

if __name__ == '__main__':
    USER_QUERY = "gemma is a local ai model google releases every so often when will gemma 4 come out"

    # Fixed search queries (what the optimizer would produce)
    SEARCH_QUERIES = [
        "latest release of Gemma AI",
        "upcoming updates from Google AI team",
        "news on new features in upcoming AI models",
    ]

    print("Warming up Ollama model...", flush=True)
    ollama_chat(MODEL, [{'role': 'user', 'content': 'hi'}])
    print("Warm-up done.\n", flush=True)

    print(f"User query: \"{USER_QUERY}\"", flush=True)
    print(f"Search queries: {SEARCH_QUERIES}", flush=True)

    # Run top-2
    r2 = run_test(SEARCH_QUERIES, max_results=2, user_query=USER_QUERY)

    print("\n  (pausing 2s between runs...)")
    time.sleep(2)

    # Run top-5
    r5 = run_test(SEARCH_QUERIES, max_results=5, user_query=USER_QUERY)

    # ── Summary ──
    print("\n" + "="*60)
    print("  RESULTS: TOP 2 vs TOP 5")
    print("="*60)
    print(f"  {'Metric':<25} {'Top 2':>10} {'Top 5':>10} {'Diff':>10}")
    print(f"  {'-'*55}")
    print(f"  {'Total results':<25} {r2['num_results']:>10} {r5['num_results']:>10} {r5['num_results']-r2['num_results']:>+10}")
    print(f"  {'Prompt size (chars)':<25} {r2['prompt_chars']:>10} {r5['prompt_chars']:>10} {r5['prompt_chars']-r2['prompt_chars']:>+10}")
    print(f"  {'Search time (s)':<25} {r2['t_search']:>10.2f} {r5['t_search']:>10.2f} {r5['t_search']-r2['t_search']:>+10.2f}")
    print(f"  {'Answer time (s)':<25} {r2['t_answer']:>10.2f} {r5['t_answer']:>10.2f} {r5['t_answer']-r2['t_answer']:>+10.2f}")
    print(f"  {'TOTAL time (s)':<25} {r2['t_total']:>10.2f} {r5['t_total']:>10.2f} {r5['t_total']-r2['t_total']:>+10.2f}")
    saved = r5['t_total'] - r2['t_total']
    pct = (saved / r5['t_total']) * 100 if r5['t_total'] > 0 else 0
    print(f"\n  -> Top 2 is {abs(saved):.2f}s {'faster' if saved > 0 else 'slower'} ({abs(pct):.1f}%)")
    print(f"  -> Top 2 had {r2['num_results']} sources, Top 5 had {r5['num_results']} sources")
