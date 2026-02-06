import requests
import json

try:
    url = "http://localhost:6006/data/plugin/scalars/tags"
    print(f"Querying {url}...")
    r = requests.get(url, timeout=2)
    if r.status_code == 200:
        print("Success! Available tags:")
        print(json.dumps(r.json(), indent=2))
    else:
        print(f"Failed with status code: {r.status_code}")
except Exception as e:
    print(f"Error: {e}")
