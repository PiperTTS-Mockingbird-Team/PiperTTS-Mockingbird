import requests

urls = [
    "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/high/en_US-ryan-high.onnx?download=true",
    "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/cori/high/en_GB-cori-high.onnx?download=true"
]

for url in urls:
    try:
        response = requests.head(url, allow_redirects=True, timeout=10)
        print(f"URL: {url}")
        print(f"Status Code: {response.status_code}")
        print("-" * 20)
    except Exception as e:
        print(f"URL: {url}")
        print(f"Error: {e}")
        print("-" * 20)
