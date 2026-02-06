import json
import os
import shutil
from pathlib import Path

def restore_latest():
    # Use current working directory or environment variable
    project_root = Path(__file__).parent.parent.resolve()
    emergency_root = project_root / "code emergency all"
    
    if not emergency_root.exists():
        print(f"Directory not found: {emergency_root}")
        return

    restored_count = 0
    print(f"Scanning: {emergency_root}")
    for folder in emergency_root.iterdir():
        if not folder.is_dir():
            continue
            
        entries_path = folder / "entries.json"
        if not entries_path.exists():
            print(f"No entries.json in {folder.name}")
            continue
            
        try:
            with open(entries_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            resource_uri = data.get("resource", "")
            print(f"Processing folder {folder.name} for {resource_uri}")
            # Convert URI to path. URI looks like file:///Users/USERNAME/...
            if resource_uri.startswith("file:///"):
                # Handle various formats:
                # file:///c%3A/Users -> C:/Users
                # file:///Users/USERNAME -> C:/Users/USERNAME (assuming C: if drive missing)
                
                path_part = resource_uri.replace("file:///", "").replace("%3A", ":").replace("%20", " ")
                if not path_part.startswith("C:") and not path_part.startswith("c:") and path_part.startswith("Users/"):
                    path_part = "C:/" + path_part
                
                target_path = Path(path_part)
                
                # Filter entries to find the latest
                entries = data.get("entries", [])
                if not entries:
                    continue
                    
                # Sort by timestamp descending
                latest_entry = max(entries, key=lambda x: x.get("timestamp", 0))
                source_file = folder / latest_entry["id"]
                
                if source_file.exists():
                    # Ensure target directory exists
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Copy to destination
                    shutil.copy2(source_file, target_path)
                    print(f"Restored: {target_path} (from {source_file.name})")
                    restored_count += 1
                else:
                    print(f"Source file missing: {source_file}")
                    
        except Exception as e:
            print(f"Error processing {folder.name}: {e}")

    print(f"\nTotal files restored: {restored_count}")

if __name__ == "__main__":
    restore_latest()
