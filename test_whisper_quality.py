"""
Test script to verify Whisper quality metrics are available
"""
import whisper
import sys
from pathlib import Path

# Test file - use command line argument or default
if len(sys.argv) > 1:
    test_wav = sys.argv[1]
else:
    test_wav = r"C:\Users\Robert\Desktop\grape ai chat test\piper_tts_server\training\make piper voice models\tts_dojo\cc_dojo\dataset\wav\1.wav"

if not Path(test_wav).exists():
    print(f"ERROR: Test file not found: {test_wav}")
    sys.exit(1)

print("Loading Whisper model (base)...")
model = whisper.load_model("base")

print(f"\nTranscribing: {Path(test_wav).name}")
result = model.transcribe(test_wav)

print("\n" + "="*60)
print("WHISPER RESULT STRUCTURE:")
print("="*60)

# Main result
print(f"\nText: {result.get('text', 'N/A')}")
print(f"\nLanguage: {result.get('language', 'N/A')}")

# Top-level metrics
print(f"\n--- TOP-LEVEL METRICS ---")
for key in ['compression_ratio', 'no_speech_prob']:
    if key in result:
        print(f"{key}: {result[key]}")
    else:
        print(f"{key}: NOT FOUND")

# Segments
segments = result.get("segments", [])
print(f"\n--- SEGMENTS ({len(segments)} total) ---")

if segments:
    for i, seg in enumerate(segments[:3]):  # Show first 3
        print(f"\nSegment {i+1}:")
        print(f"  Text: {seg.get('text', 'N/A')}")
        print(f"  no_speech_prob: {seg.get('no_speech_prob', 'NOT FOUND')}")
        print(f"  avg_logprob: {seg.get('avg_logprob', 'NOT FOUND')}")
        print(f"  compression_ratio: {seg.get('compression_ratio', 'NOT FOUND')}")
    
    # Calculate averages like our filter does
    print("\n--- CALCULATED AVERAGES (for filtering) ---")
    avg_no_speech = sum(s.get("no_speech_prob", 0) for s in segments) / len(segments)
    avg_logprob = sum(s.get("avg_logprob", 0) for s in segments) / len(segments)
    # FIXED: Compression ratio is per-segment, not top-level
    compression = sum(s.get("compression_ratio", 0) for s in segments) / len(segments)
    
    print(f"Average no_speech_prob: {avg_no_speech:.4f} (threshold: > 0.6)")
    print(f"Average avg_logprob: {avg_logprob:.4f} (threshold: < -1.0)")
    print(f"Compression ratio: {compression:.4f} (threshold: > 2.4)")
    
    # Check if it would be filtered
    print("\n--- FILTER DECISION ---")
    if avg_no_speech > 0.6:
        print(f"❌ WOULD BE SKIPPED: Likely silence/noise (no_speech_prob={avg_no_speech:.2f})")
    elif avg_logprob < -1.0:
        print(f"❌ WOULD BE SKIPPED: Low confidence (avg_logprob={avg_logprob:.2f})")
    elif compression > 2.4:
        print(f"❌ WOULD BE SKIPPED: Hallucination/repetition (compression={compression:.2f})")
    else:
        print(f"✅ WOULD PASS: All quality checks passed")
else:
    print("WARNING: No segments found in result!")

print("\n" + "="*60)
print("All available keys in result:")
print(result.keys())
print("="*60)
