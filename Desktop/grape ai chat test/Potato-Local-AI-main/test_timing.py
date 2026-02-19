"""
Pipeline Timing Test
Measures how long each step takes when processing a query.
Uses the exact same functions your app calls.
"""
import time

QUERY = "is humanity destined for the stars"

print("=" * 60)
print(f"  PIPELINE TIMING TEST")
print(f"  Query: \"{QUERY}\"")
print("=" * 60)

# -- Step 1: needs_internet_search ----------------------------
from ddgsearch import needs_internet_search

print(f"\n[STEP 1] needs_internet_search()")
t1_start = time.time()
do_search = needs_internet_search(QUERY)
t1_end = time.time()
t1 = t1_end - t1_start
print(f"  Result:  {do_search}")
print(f"  Time:    {t1:.1f}s")

# -- Step 2: analyze_and_optimize_query -----------------------
from ddgsearch import analyze_and_optimize_query

print(f"\n[STEP 2] analyze_and_optimize_query()")
t2_start = time.time()
if do_search:
    search_queries = analyze_and_optimize_query(QUERY)
else:
    search_queries = []
t2_end = time.time()
t2 = t2_end - t2_start
print(f"  Queries: {search_queries}")
print(f"  Time:    {t2:.1f}s")

# -- Step 3: perform_concurrent_searches (DuckDuckGo) --------
from ddgsearch import perform_concurrent_searches

print(f"\n[STEP 3] perform_concurrent_searches()")
t3_start = time.time()
if search_queries:
    search_results, search_errors = perform_concurrent_searches(search_queries)
else:
    search_results, search_errors = [], set()
t3_end = time.time()
t3 = t3_end - t3_start
print(f"  Results: {len(search_results)} found, errors: {search_errors or 'none'}")
print(f"  Time:    {t3:.1f}s")

# -- Step 4: Final Ollama answer ------------------------------
import ollama
from datetime import datetime

print(f"\n[STEP 4] Ollama final answer (streaming)")
t4_start = time.time()
current_date = datetime.now().strftime("%A, %B %d, %Y")

if search_results:
    search_context = "\n".join([f"- {r.get('body')}" for r in search_results])
    prompt = (
        f"Current Date: {current_date}\n\n"
        f"Search Results:\n{search_context}\n\n"
        f"Instructions: Use the Search Results and Current Date above to answer the question below. "
        "Be very direct. If the answer is in the text, use it. If not, give your best answer.\n\n"
        f"User Question: {QUERY}\n\n"
        "Answer:"
    )
else:
    prompt = (
        f"Current Date: {current_date}\n\n"
        f"Instructions: Answer the question below directly and helpfully.\n\n"
        f"User Question: {QUERY}\n\n"
        "Answer:"
    )

first_token_time = None
try:
    stream = ollama.chat(
        model='qwen2.5:1.5b',
        messages=[{'role': 'user', 'content': prompt}],
        stream=True
    )
    answer = ""
    for chunk in stream:
        token = chunk['message']['content']
        if first_token_time is None:
            first_token_time = time.time()
        answer += token
except Exception as e:
    answer = f"ERROR: {e}"

t4_end = time.time()
t4 = t4_end - t4_start
t4_first = (first_token_time - t4_start) if first_token_time else t4
print(f"  First token: {t4_first:.1f}s")
print(f"  Full answer: {t4:.1f}s")
print(f"  Preview:     {answer[:150]}...")

# -- Summary -------------------------------------------------
total = t1 + t2 + t3 + t4
print("\n" + "=" * 60)
print("  SUMMARY")
print("=" * 60)
print(f"  Step 1 - Internet search? (Ollama)    {t1:6.1f}s")
print(f"  Step 2 - Optimize queries (Ollama)    {t2:6.1f}s")
print(f"  Step 3 - DuckDuckGo search            {t3:6.1f}s")
print(f"  Step 4 - Final answer (Ollama)        {t4:6.1f}s")
print(f"           |- Time to first token       {t4_first:6.1f}s")
print(f"           +- Generation time           {t4 - t4_first:6.1f}s")
print(f"  ----------------------------------------------")
print(f"  TOTAL                                 {total:6.1f}s")
print(f"  Ollama time (steps 1+2+4)             {t1+t2+t4:6.1f}s")
print(f"  Search time (step 3)                  {t3:6.1f}s")
print("=" * 60)
