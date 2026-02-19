import sys
import time
import io
import requests
import os
from ddgs import DDGS
from datetime import datetime

# Disable proxies which might cause hangs in this terminal environment
os.environ['no_proxy'] = '*'
os.environ['http_proxy'] = ''
os.environ['https_proxy'] = ''

# 1. Encoding & Buffering Fixes
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Disable output buffering
try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

MODEL = 'qwen2.5:1.5b'

import requests

def get_answer(user_query, results):
    """Generates an answer using Ollama via direct requests."""
    context = "\n".join(f"- {r.get('body', '')}" for r in results)
    current_date = datetime.now().strftime("%A, %B %d, %Y")
    
    prompt = (
        f"Current Date: {current_date}\n\n"
        f"Search Results:\n{context}\n\n"
        f"Use the search results to answer the question. Be direct and concise.\n\n"
        f"Question: {user_query}\n\nAnswer:"
    )
    
    t0 = time.perf_counter()
    try:
        r = requests.post(
            'http://127.0.0.1:11434/api/chat',
            json={
                'model': MODEL,
                'messages': [{'role': 'user', 'content': prompt}],
                'stream': False
            },
            timeout=180
        )
        r.raise_for_status()
        content = r.json()['message']['content']
    except Exception as e:
        content = f"Error calling Ollama: {e}"
    
    elapsed = time.perf_counter() - t0
    return content, elapsed, len(prompt)


def perform_search(queries, max_results):
    """Performs sequential searches for stability."""
    all_results = []
    t0 = time.perf_counter()
    
    with DDGS(timeout=10) as ddgs:
        for q in queries:
            try:
                print(f"  Searching: '{q}' (max {max_results})...", flush=True)
                results = list(ddgs.text(q, max_results=max_results))
                all_results.extend([r for r in results if 'body' in r])
            except Exception as e:
                print(f"  Search error for '{q}': {e}", flush=True)
                
    elapsed = time.perf_counter() - t0
    return all_results, elapsed

def run_benchmark():
    user_query = "gemma is a local ai model google releases every so often when will gemma 4 come out"
    search_queries = [
        "latest release of Google Gemma AI",
        "Google Gemma roadmap news 2024 2025",
        "Gemma 2 vs Gemma 3 vs Gemma 4 release dates"
    ]

    print(f"Benchmark: {MODEL} | Top 2 vs Top 5", flush=True)
    print(f"Query: {user_query}\n", flush=True)

    # --- TOP 2 RUN ---
    print("--- Running Top 2 Test ---", flush=True)
    results_2, t_search_2 = perform_search(search_queries, max_results=2)
    ans_2, t_ans_2, p_size_2 = get_answer(user_query, results_2)
    total_2 = t_search_2 + t_ans_2
    print(f"  Done. Total time: {total_2:.2f}s\n", flush=True)

    time.sleep(2) # Cooldown

    # --- TOP 5 RUN ---
    print("--- Running Top 5 Test ---", flush=True)
    results_5, t_search_5 = perform_search(search_queries, max_results=5)
    ans_5, t_ans_5, p_size_5 = get_answer(user_query, results_5)
    total_5 = t_search_5 + t_ans_5
    print(f"  Done. Total time: {total_5:.2f}s\n", flush=True)

    # --- RESULTS ---
    print("="*60, flush=True)
    print(f"{'Metric':<20} | {'Top 2':>10} | {'Top 5':>10} | {'Diff':>10}", flush=True)
    print("-" * 60, flush=True)
    print(f"{'Results Count':<20} | {len(results_2):>10} | {len(results_5):>10} | {len(results_5)-len(results_2):>+10}", flush=True)
    print(f"{'Prompt Size':<20} | {p_size_2:>10} | {p_size_5:>10} | {p_size_5-p_size_2:>+10}", flush=True)
    print(f"{'Search Time (s)':<20} | {t_search_2:>10.2f} | {t_search_5:>10.2f} | {t_search_5-t_search_2:>+10.2f}", flush=True)
    print(f"{'Answer Time (s)':<20} | {t_ans_2:>10.2f} | {t_ans_5:>10.2f} | {t_ans_5-t_ans_2:>+10.2f}", flush=True)
    print(f"{'TOTAL Time (s)':<20} | {total_2:>10.2f} | {total_5:>10.2f} | {total_5-total_2:>+10.2f}", flush=True)
    print("="*60, flush=True)

    gain = total_5 - total_2
    pct = (gain / total_5 * 100) if total_5 > 0 else 0
    print(f"\nTop 2 is {abs(gain):.2f}s {'faster' if gain > 0 else 'slower'} ({abs(pct):.1f}%)", flush=True)

if __name__ == "__main__":
    try:
        print("Starting Benchmark script...", flush=True)
        run_benchmark()
    except Exception as e:
        import traceback
        print(f"\nFATAL ERROR: {e}", flush=True)
        traceback.print_exc()
