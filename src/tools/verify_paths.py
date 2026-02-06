"""
Quick test script to verify that the folder structure and key files are in the correct locations.
This is useful after reorganization or installation to ensure everything is where the server expects it.
"""
from pathlib import Path

# Define the source directory (where the main logic resides)
SCRIPT_DIR = Path(__file__).resolve().parent.parent
print(f"SCRIPT_DIR (src): {SCRIPT_DIR}")
print(f"  Exists: {SCRIPT_DIR.exists()}")

# Check the voices folder (should be in the parent directory of src/)
voices_dir = SCRIPT_DIR.parent / "voices"
print(f"\nVoices folder: {voices_dir}")
print(f"  Exists: {voices_dir.exists()}")
if voices_dir.exists():
    # List all .onnx voice models found
    voices = list(voices_dir.rglob("*.onnx"))
    print(f"  Found {len(voices)} voice(s)")
    for v in voices:
        print(f"    - {v.name}")

# Check for the Piper executable (Windows specific check here)
piper_exe = SCRIPT_DIR / "piper" / "piper.exe"
print(f"\nPiper executable: {piper_exe}")
print(f"  Exists: {piper_exe.exists()}")

# Check for the server configuration file
config_path = SCRIPT_DIR / "config.json"
print(f"\nConfig file: {config_path}")
print(f"  Exists: {config_path.exists()}")

# Check for the Python requirements file
req_path = SCRIPT_DIR / "requirements.txt"
print(f"\nRequirements: {req_path}")
print(f"  Exists: {req_path.exists()}")

# Check for the tools directory and its scripts
tools_dir = SCRIPT_DIR / "tools"
print(f"\nTools folder: {tools_dir}")
print(f"  Exists: {tools_dir.exists()}")
if tools_dir.exists():
    start_ps1 = tools_dir / "start_piper_server.ps1"
    start_bat = tools_dir / "start_piper_server.bat"
    print(f"  start_piper_server.ps1: {start_ps1.exists()}")
    print(f"  start_piper_server.bat: {start_bat.exists()}")

# Check for the voice addition guide
voices_guide = SCRIPT_DIR.parent / "voices" / "HOW_TO_ADD_VOICES.md"
print(f"\nVoices guide: {voices_guide}")
print(f"  Exists: {voices_guide.exists()}")

print("\n" + "="*60)
# Final verification summary
if all([
    SCRIPT_DIR.exists(),
    voices_dir.exists(),
    piper_exe.exists(),
    config_path.exists(),
    req_path.exists(),
    tools_dir.exists(),
    voices_guide.exists()
]):
    print("✅ All paths verified - structure looks good!")
else:
    print("⚠️  Some paths are missing - check the details above")
