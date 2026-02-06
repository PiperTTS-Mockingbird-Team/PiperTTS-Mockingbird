"""
Utility script to check if the male and female voice model files (.onnx) are actually different.
It compares file sizes and SHA256 hashes to detect accidental duplicates.
"""
import hashlib
from pathlib import Path

# Define paths relative to the script location
script_dir = Path(__file__).resolve().parent
voices_dir = script_dir.parent / "voices"

# Paths to the specific voice model files
female_voice = voices_dir / "female" / "en_US-hfc_female-medium.onnx"
male_voice = voices_dir / "male" / "en_US-hfc_male-medium.onnx"

def file_hash(path):
    """
    Calculate the SHA256 hash of a file to uniquely identify its content.
    Reads the file in chunks to handle large files efficiently.
    """
    sha256 = hashlib.sha256()
    with open(path, 'rb') as f:
        while chunk := f.read(8192):
            sha256.update(chunk)
    return sha256.hexdigest()

print("Checking voice files...\n")

# Check and hash the female voice model
if female_voice.exists():
    print(f"Female voice: {female_voice}")
    print(f"  Size: {female_voice.stat().st_size:,} bytes")
    female_hash = file_hash(female_voice)
    print(f"  Hash: {female_hash[:16]}...")
else:
    print(f"Female voice NOT FOUND: {female_voice}")
    female_hash = None

print()

# Check and hash the male voice model
if male_voice.exists():
    print(f"Male voice: {male_voice}")
    print(f"  Size: {male_voice.stat().st_size:,} bytes")
    male_hash = file_hash(male_voice)
    print(f"  Hash: {male_hash[:16]}...")
else:
    print(f"Male voice NOT FOUND: {male_voice}")
    male_hash = None

print()

# Compare the hashes of the two files
if female_hash and male_hash:
    if female_hash == male_hash:
        print("⚠️  FILES ARE IDENTICAL! Both voices are the same file.")
        print("    You need to download the actual male voice model.")
    else:
        print("✓ Files are different - voices should sound different.")
else:
    print("Cannot compare - one or both files are missing.")
