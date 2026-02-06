import zipfile
import sys
import os

filepath = "make piper voice models/tts_dojo/feeet_dojo/pretrained_tts_checkpoint/epoch=2164-step=1355540.ckpt"

if not os.path.exists(filepath):
    print(f"File not found: {filepath}")
    sys.exit(1)

print(f"Testing file: {filepath}")
print(f"Size: {os.path.getsize(filepath)} bytes")

try:
    with zipfile.ZipFile(filepath, 'r') as zip_ref:
        result = zip_ref.testzip()
        if result is None:
            print("Zip check PASSED: file is a valid zip and data is intact.")
        else:
            print(f"Zip check FAILED: first corrupted file found: {result}")
except zipfile.BadZipFile as e:
    print(f"BadZipFile error: {e}")
except Exception as e:
    print(f"Error checking zip: {e}")
