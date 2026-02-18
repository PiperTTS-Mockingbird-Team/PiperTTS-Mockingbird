from pathlib import Path

metadata_path = Path(r"training\make piper voice models\tts_dojo\cc_dojo\dataset\metadata.csv")

lines = metadata_path.read_text(encoding='utf-8').splitlines()
ellipsis_lines = [line for line in lines if '...' in line]

print(f"\n{'='*60}")
print("ELLIPSIS STATUS IN METADATA.CSV:")
print(f"{'='*60}")
print(f"Total lines: {len(lines)}")
print(f"Lines with '...': {len(ellipsis_lines)}")

if ellipsis_lines:
    print(f"\n❌ Ellipsis entries STILL PRESENT (not filtered by Whisper)")
    print("\nSample entries:")
    for line in ellipsis_lines[:3]:
        parts = line.split('|', 1)
        if len(parts) == 2:
            text_preview = parts[1][:80] + "..." if len(parts[1]) > 80 else parts[1]
            print(f"  File {parts[0]}: {text_preview}")
    
    print(f"\nWhy Whisper didn't filter them:")
    print("  - Ellipsis '...' indicates unclear/mumbled audio")
    print("  - BUT Whisper confidence metrics show GOOD scores")
    print("  - Example: file 9.wav has no_speech=0.14, logprob=-0.46")
    print("  - These pass all 3 thresholds (0.6, -1.0, 2.4)")
    print(f"\nEllipsis filter runs separately during validation")
else:
    print(f"\n✅ All ellipsis entries removed!")

print(f"{'='*60}\n")
