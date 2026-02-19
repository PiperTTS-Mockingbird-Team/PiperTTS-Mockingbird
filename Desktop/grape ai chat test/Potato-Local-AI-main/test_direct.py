"""
Minimal test: Call Ollama directly with the exact same big system prompt 
that needs_internet_search uses. No ddgsearch import.
"""
import time
import ollama

QUERY = "is humanity destined for the stars"

NEEDS_SEARCH_SYSTEM_MSG = """Decide if a question needs an internet search. Reply ONLY: YES or NO

YES - needs internet:
- Current events, news, weather, prices, stocks, sports results
- Questions about events after 2023 or with years like 2024, 2025, 2026
- Real-time data: "what time is it in...", "weather in...", "price of..."
- Specific products, releases, or schedules that change
- Questions about specific real people

NO - does NOT need internet:
- Writing/creating: "write a poem", "write code", "create a story"
- Math/logic: "what is 2+2", "solve this equation"
- Conversation: "hello", "tell me a joke", "how are you"
- Definitions: "what does ephemeral mean"
- Explaining concepts: "what is recursion", "explain gravity"

When in doubt, say YES.
Reply with ONLY: YES or NO"""

print("Test: Big system prompt with ollama.chat() directly...")
start = time.time()
try:
    response = ollama.chat(
        model='qwen2.5:1.5b',
        messages=[
            {'role': 'system', 'content': NEEDS_SEARCH_SYSTEM_MSG},
            {'role': 'user', 'content': QUERY}
        ]
    )
    elapsed = time.time() - start
    print(f"Result: {response['message']['content'].strip()}")
    print(f"Time: {elapsed:.1f}s")
    total_dur = response.get('total_duration', 0) / 1e9
    load_dur = response.get('load_duration', 0) / 1e9
    prompt_dur = response.get('prompt_eval_duration', 0) / 1e9
    prompt_tokens = response.get('prompt_eval_count', 0)
    eval_dur = response.get('eval_duration', 0) / 1e9
    eval_tokens = response.get('eval_count', 0)
    print(f"Model load: {load_dur:.2f}s")
    print(f"Prompt eval: {prompt_dur:.2f}s ({prompt_tokens} tokens)")
    print(f"Generation: {eval_dur:.2f}s ({eval_tokens} tokens)")
except Exception as e:
    elapsed = time.time() - start
    print(f"ERROR after {elapsed:.1f}s: {type(e).__name__}: {e}")
