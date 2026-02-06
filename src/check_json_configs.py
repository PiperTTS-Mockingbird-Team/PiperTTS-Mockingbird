"""
Utility script to compare the .json configuration files for the male and female voices.
This helps ensure that the models are configured correctly and are not just duplicates.
"""
import json
from pathlib import Path

# Define paths relative to the script location
script_dir = Path(__file__).resolve().parent
voices_dir = script_dir / "voices"

# Paths to the specific voice configuration files
female_json = voices_dir / "female" / "en_US-hfc_female-medium.onnx.json"
male_json = voices_dir / "male" / "en_US-hfc_male-medium.onnx.json"

print("Checking .json config files...\n")

# Load and display info for the female voice config
if female_json.exists():
    female_data = json.loads(female_json.read_text(encoding='utf-8'))
    print(f"Female config: {female_json.name}")
    print(f"  Language: {female_data.get('language', {}).get('code', 'N/A')}")
    print(f"  Dataset: {female_data.get('dataset', 'N/A')}")
    print(f"  Sample rate: {female_data.get('audio', {}).get('sample_rate', 'N/A')}")
else:
    print(f"Female config NOT FOUND")
    female_data = None

print()

# Load and display info for the male voice config
if male_json.exists():
    male_data = json.loads(male_json.read_text(encoding='utf-8'))
    print(f"Male config: {male_json.name}")
    print(f"  Language: {male_data.get('language', {}).get('code', 'N/A')}")
    print(f"  Dataset: {male_data.get('dataset', 'N/A')}")
    print(f"  Sample rate: {male_data.get('audio', {}).get('sample_rate', 'N/A')}")
else:
    print(f"Male config NOT FOUND")
    male_data = None

print()

# Compare the two configuration files
if female_data and male_data:
    if female_data == male_data:
        print("⚠️  CONFIG FILES ARE IDENTICAL!")
        print("    This means both .onnx files will be processed the same way.")
        print("    You may have accidentally copied the female config to the male folder.")
    else:
        print("✓ Config files are different.")
