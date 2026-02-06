import requests
import json
import sys

BASE_URL = "http://localhost:6006"

def check_tensorboard():
    print(f"Checking TensorBoard at {BASE_URL}...")
    
    # 1. Get Tags
    try:
        resp = requests.get(f"{BASE_URL}/data/plugin/scalars/tags")
        if resp.status_code != 200:
            print(f"Error fetching tags: {resp.status_code}")
            return
        
        tags_data = resp.json()
        print("\n--- Available Tags ---")
        found_mel = False
        for run, tags in tags_data.items():
            print(f"Run: {run}")
            for tag in tags:
                print(f"  - {tag}")
                if "mel" in tag:
                    found_mel = True
        
        if not found_mel:
            print("\n[WARNING] No 'mel' tag found in the list above.")
        else:
            print("\n[SUCCESS] Found 'mel' related tag.")

        # 2. Try to fetch specific values
        target_tags = ["loss_mel", "loss_gen_all", "loss_disc_all"]
        print("\n--- Fetching Specific Values (run=version_0) ---")
        for tag in target_tags:
            url = f"{BASE_URL}/data/plugin/scalars/scalars?tag={tag}&run=version_0"
            r = requests.get(url)
            if r.status_code == 200:
                data = r.json()
                if data:
                    last_point = data[-1] # [wall_time, step, value]
                    print(f"{tag}: {last_point[2]} (Step: {last_point[1]})")
                else:
                    print(f"{tag}: No data points yet")
            else:
                print(f"{tag}: HTTP {r.status_code} (Likely tag doesn't exist)")

    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    check_tensorboard()
