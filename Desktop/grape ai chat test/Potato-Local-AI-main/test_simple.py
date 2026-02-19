import ollama
import time

print("Starting simple test...")
try:
    start = time.time()
    response = ollama.chat(model='qwen2.5:1.5b', messages=[{'role': 'user', 'content': 'hi'}])
    end = time.time()
    print(f"Ollama responded in {end-start:.2f}s")
    print(f"Response: {response['message']['content']}")
except Exception as e:
    print(f"Error: {e}")
