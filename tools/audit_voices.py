import os
import json
from pathlib import Path

def audit_voices():
    # Define paths relative to the script location
    script_dir = Path(__file__).resolve().parent
    voices_dir = script_dir.parent / "voices"
    
    print("=" * 60)
    print("PIPER TTS VOICE AUDIT TOOL")
    print("=" * 60)
    print(f"Scanning directory: {voices_dir}\n")

    found_files = list(voices_dir.rglob("*.onnx"))
    
    if not found_files:
        print("No .onnx voice files found.")
        return

    results = []
    
    # Expected size ranges (in MB)
    EXPECTED_SIZE = {
        "low": (20, 35),
        "medium": (50, 75),
        "high": (100, 150)
    }

    for onnx_path in found_files:
        file_name = onnx_path.name
        size_mb = onnx_path.stat().st_size / (1024 * 1024)
        
        # Determine quality from filename
        quality_label = "unknown"
        if "-high" in file_name.lower() or "_high" in file_name.lower():
            quality_label = "high"
        elif "-medium" in file_name.lower() or "_medium" in file_name.lower():
            quality_label = "medium"
        elif "-low" in file_name.lower() or "_low" in file_name.lower():
            quality_label = "low"

        # Check JSON config if it exists
        json_path = onnx_path.with_suffix(".onnx.json")
        json_quality = "not found"
        if json_path.exists():
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    json_quality = config.get("audio", {}).get("quality", "missing")
            except Exception as e:
                json_quality = f"error: {str(e)[:15]}"

        # Audit logic
        issues = []
        if quality_label in EXPECTED_SIZE:
            min_size, max_size = EXPECTED_SIZE[quality_label]
            if not (min_size <= size_mb <= max_size):
                issues.append("Size Mismatch")
        
        # Also compare filename label with JSON label if possible
        if json_quality not in ["not found", "missing", "training_folder"] and not json_quality.startswith("error"):
            if quality_label != "unknown" and quality_label != json_quality:
                issues.append("JSON Label Mismatch")

        status = "OK"
        if issues:
            status = " & ".join(issues)

        results.append({
            "name": file_name,
            "size": size_mb,
            "label": quality_label,
            "json_quality": json_quality,
            "status": status,
            "path": onnx_path
        })

    # Print results
    print(f"{'Voice File':<40} | {'Size MB':<8} | {'Label':<7} | {'JSON':<10} | {'Status'}")
    print("-" * 100)
    
    mismatches = 0
    for res in results:
        status_str = res['status']
        if status_str != "OK":
            status_str = f"⚠️  {status_str}"
            mismatches += 1
            
        print(f"{res['name']:<40} | {res['size']:>8.2f} | {res['label']:<7} | {res['json_quality']:<10} | {status_str}")

    print("\n" + "=" * 60)
    print(f"Audit Complete: {len(results)} files scanned, {mismatches} issues found.")
    print("=" * 60)
    
    if mismatches > 0:
        print("\nRecommendations:")
        for res in results:
            if res['status'] != "OK":
                if "Size" in res['status']:
                    print(f"- {res['name']}: Is labeled '{res['label']}' but size ({res['size']:.2f}MB) suggests a different quality level.")
                if "JSON" in res['status']:
                    print(f"- {res['name']}: Filename label ('{res['label']}') and JSON label ('{res['json_quality']}') do not match.")

if __name__ == "__main__":
    audit_voices()
