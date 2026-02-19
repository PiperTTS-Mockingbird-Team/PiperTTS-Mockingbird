import requests
import time
import os

# Disable proxies
os.environ['no_proxy'] = '*'
os.environ['http_proxy'] = ''
os.environ['https_proxy'] = ''

MODEL = 'qwen2.5:1.5b'

def test_ollama():
    print("Sending request to Ollama...", flush=True)
    t0 = time.time()
    try:
        r = requests.post(
            'http://127.0.0.1:11434/api/chat',
            json={
                'model': MODEL,
                'messages': [{'role': 'user', 'content': 'Say "Ollama works"'}],
                'stream': False
            },
            timeout=30
        )
        print(f"Response ({time.time()-t0:.2f}s): {r.json()['message']['content']}")
    except Exception as e:
        print(f"Error ({time.time()-t0:.2f}s): {e}")

if __name__ == "__main__":
    test_ollama()
