"""
Test: Is Ollama reloading the model between calls?
Makes 3 back-to-back calls to the same model with tiny prompts.
If model stays loaded, calls 2 and 3 should be much faster than call 1.
"""
import time
import ollama

MODEL = 'qwen2.5:1.5b'

print("=" * 60)
print("  OLLAMA MODEL RELOAD TEST")
print(f"  Model: {MODEL}")
print("=" * 60)

prompts = [
    "Reply with only YES",
    "Reply with only NO", 
    "Reply with only OK",
]

for i, prompt in enumerate(prompts, 1):
    start = time.time()
    response = ollama.chat(
        model=MODEL,
        messages=[{'role': 'user', 'content': prompt}]
    )
    elapsed = time.time() - start
    answer = response['message']['content'].strip()
    
    # Check timing details from response
    total_dur = response.get('total_duration', 0) / 1e9        # nanoseconds -> seconds
    load_dur = response.get('load_duration', 0) / 1e9
    prompt_dur = response.get('prompt_eval_duration', 0) / 1e9
    eval_dur = response.get('eval_duration', 0) / 1e9
    prompt_tokens = response.get('prompt_eval_count', 0)
    eval_tokens = response.get('eval_count', 0)
    
    print(f"\n  Call {i}: \"{prompt}\"")
    print(f"    Answer:         {answer}")
    print(f"    Wall clock:     {elapsed:.2f}s")
    print(f"    -- Ollama internal breakdown --")
    print(f"    Model load:     {load_dur:.2f}s")
    print(f"    Prompt eval:    {prompt_dur:.2f}s  ({prompt_tokens} tokens)")
    print(f"    Generation:     {eval_dur:.2f}s  ({eval_tokens} tokens)")
    print(f"    Total (Ollama): {total_dur:.2f}s")

print("\n" + "=" * 60)
print("  If 'Model load' is high on every call, it's reloading.")
print("  If only call 1 has high load, the model stays cached.")
print("=" * 60)
