import os
import json
from pathlib import Path

def audit_pretrained():
    # Define paths relative to the script location
    script_dir = Path(__file__).resolve().parent
    pretrained_dir = script_dir.parent / "training" / "make piper voice models" / "tts_dojo" / "PRETRAINED_CHECKPOINTS" / "default" / "shared"
    
    print("=" * 80)
    print("PIPER SHARED CHECKPOINT AUDIT")
    print("=" * 80)
    print(f"Scanning directory: {pretrained_dir}\n")

    if not pretrained_dir.exists():
        print(f"Error: Directory not found: {pretrained_dir}")
        return

    # Expected size ranges for .ckpt files
    EXPECTED_SIZES = {
        "high": (900, 1100),
        "medium": (750, 890),
        "low": (350, 500)
    }

    found_issues = 0
    
    for quality in ["low", "medium", "high"]:
        q_dir = pretrained_dir / quality
        if not q_dir.exists():
            continue
            
        ckpt_files = list(q_dir.glob("*.ckpt"))
        if not ckpt_files:
            print(f"  [{quality:<6}] (No files)")
            continue
            
        for ckpt in ckpt_files:
            size_mb = ckpt.stat().st_size / (1024 * 1024)
            status = "OK"
            
            min_s, max_s = EXPECTED_SIZES.get(quality, (0, 9999))
            if not (min_s <= size_mb <= max_s):
                status = f"⚠️  MISMATCH (Actual: {size_mb:.2f}MB, Expected range for {quality})"
                found_issues += 1
            
            print(f"  [{quality:<6}] {ckpt.name:<40} | {size_mb:>8.2f} MB | {status}")

    print("\n" + "=" * 80)
    print(f"Audit Complete: {found_issues} issues found.")
    print("=" * 80)
    
    if found_issues > 0:
        print("\nUrgent Actions Required:")
        print("1. Your 'M_voice/medium' folder appears to contain 'Low' quality files.")
        print("2. Models started using these files will be stuck at Low quality regardless of settings.")

if __name__ == "__main__":
    audit_pretrained()
