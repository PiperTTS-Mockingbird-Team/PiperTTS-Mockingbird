import os
import sys
import subprocess
import time
import re
from pathlib import Path

def log(msg):
    print(f"[TRANSCRIPTION] {msg}")
    sys.stdout.flush()

def validate_and_fix_metadata_csv(csv_path):
    """
    Validates and fixes common issues in metadata.csv files:
    1. Ensures delimiter is '|' (not ',')
    2. Removes blank lines that cause preprocessing errors
    3. Verifies all referenced audio files exist
    4. Removes entries for missing audio files
    
    Returns: (is_valid, num_fixes, error_messages)
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        return (False, 0, ["Metadata file does not exist"])
    
    try:
        content = csv_path.read_text(encoding='utf-8')
    except Exception as e:
        return (False, 0, [f"Could not read metadata file: {e}"])
    
    lines = content.splitlines()
    if not lines:
        return (False, 0, ["Metadata file is empty"])
    
    fixes = 0
    errors = []
    valid_lines = []
    dataset_dir = csv_path.parent
    
    # Check 1: Delimiter validation (should be | not ,)
    first_line = lines[0] if lines else ""
    if ',' in first_line and '|' not in first_line:
        log("WARNING: Metadata uses ',' delimiter. Expected '|' for Piper compatibility.")
        errors.append("Delimiter is ',' but Piper expects '|' (not auto-fixed)")
    
    # Check 2 & 3: Remove blank lines and validate audio file existence
    for line_num, line in enumerate(lines, 1):
        # Remove blank/whitespace-only lines
        if not line.strip():
            fixes += 1
            continue
        
        # Parse line: expected format is "filename.wav|transcription text"
        parts = line.split('|', 1)
        if len(parts) < 2:
            errors.append(f"Line {line_num}: Invalid format (missing | delimiter)")
            continue
        
        audio_filename = parts[0].strip()
        
        # Skip validation if filename looks like a placeholder or comment
        if audio_filename.startswith('#') or not audio_filename:
            continue
        
        # Check if referenced audio file exists
        audio_path = dataset_dir / audio_filename
        if not audio_path.exists():
            log(f"WARNING: Audio file missing: {audio_filename}")
            fixes += 1
            errors.append(f"Line {line_num}: Missing audio file {audio_filename} (entry removed)")
            continue
        
        # Line is valid - keep it
        valid_lines.append(line)
    
    # If fixes were made, rewrite the file
    if fixes > 0:
        try:
            new_content = '\n'.join(valid_lines)
            if new_content and not new_content.endswith('\n'):
                new_content += '\n'
            csv_path.write_text(new_content, encoding='utf-8')
            log(f"Fixed {fixes} issue(s) in metadata.csv")
        except Exception as e:
            errors.append(f"Could not write fixed metadata: {e}")
            return (False, fixes, errors)
    
    is_valid = len(errors) == 0 or all('not auto-fixed' in e or 'entry removed' in e for e in errors)
    return (is_valid, fixes, errors)

def ensure_dependencies():
    """Ensure whisper and its requirements are installed."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        import whisper
    except ImportError:
        log("Whisper not found. Installing OpenAI Whisper (this will take a moment)...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "openai-whisper"], creationflags=flags)
    
    # Check for ffmpeg (required by whisper)
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True, creationflags=flags)
        return # FFmpeg exists
    except (FileNotFoundError, subprocess.CalledProcessError):
        log("WARNING: ffmpeg not found. Transcription will likely fail.")
        
        if os.name == 'nt':
            # [STABILITY] Automatically try to install FFmpeg on Windows via winget.
            # This handles the most common reason for transcription failure (missing encoder).
            log("Attempting to install ffmpeg via winget (requires internet)...")
            try:
                # OPTIMIZATION: Use --silent to prevent hanging on prompts
                res = subprocess.run(
                    [
                        "winget",
                        "install",
                        "Gyan.FFmpeg",
                        "--accept-source-agreements",
                        "--accept-package-agreements",
                        "--silent",
                    ],
                    creationflags=flags,
                )
                if res.returncode == 0:
                    log("ffmpeg installation successful. Please restart the app if transcription still fails.")
                    return
            except Exception as e:
                log(f"Auto-install failed: {e}")

        log("Please install ffmpeg manually: https://ffmpeg.org/")


def transcribe_files(wav_files, progress_callback=None, *, model_name: str = "base"):
    """Transcribe a specific list of WAV files.

    Returns a list of (id, text) tuples where id is the WAV stem.
    """
    wav_files = [Path(p) for p in (wav_files or [])]
    wav_files = [p for p in wav_files if p.exists() and p.is_file()]
    if not wav_files:
        return []

    # Sort files naturally (1.wav, 2.wav, 10.wav instead of 1.wav, 10.wav, 2.wav)
    wav_files.sort(key=lambda p: int(p.stem) if p.stem.isdigit() else p.stem)

    ensure_dependencies()
    import whisper
    from tqdm import tqdm

    log(f"Loading AI Model ({model_name})...")
    model = whisper.load_model(model_name)

    results = []
    total = len(wav_files)

    log(f"Starting transcription of {total} files...")
    if progress_callback:
        progress_callback(0, total, "Initializing...")

    print()  # Buffer
    for i, wav in enumerate(tqdm(wav_files, desc="Transcribing", unit="file", bar_format="{l_bar}{bar:30}{r_bar}")):
        try:
            if progress_callback:
                progress_callback(i, total, f"Transcribing {wav.name}")

            result = model.transcribe(str(wav))
            text = (result.get("text") or "").strip()
            if text:
                results.append((wav.stem, text))
        except Exception as e:
            tqdm.write(f"[ERROR] Transcribing {wav.name}: {e}")

    if progress_callback:
        progress_callback(total, total, "Finalizing...")

    return results

def transcribe_folder(dataset_folder, progress_callback=None):
    """
    [STEP 3] AUTO-TRAIN FLOW: Automated Transcription
    
    This function generates the `metadata.csv` required by Piper.
    1. Loads the OpenAI Whisper AI model.
    2. Reads every WAV file in the given `dataset_folder`.
    3. [OPTIMIZATION] Skips files that are already transcribed in metadata.csv.
    4. Transcribes the audio to text.
    5. Writes `metadata.csv` in the format: filename|text
    """
    dataset_path = Path(dataset_folder)
    wav_files = list(dataset_path.glob("*.wav"))

    if not wav_files:
        log(f"No WAV files found in {dataset_path}")
        return

    # Check for existing metadata to avoid re-transcribing everything
    metadata_path = dataset_path / "metadata.csv"
    existing = {}
    if metadata_path.exists():
        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                for line in f:
                    if "|" in line:
                        k, v = line.split("|", 1)
                        if v.strip():
                            existing[k.strip()] = v.strip()
        except Exception as e:
            log(f"Warning: Could not read existing metadata: {e}")

    # Filter out already-transcribed files
    to_transcribe = [f for f in wav_files if f.stem not in existing]
    
    if not to_transcribe:
        log("All files already transcribed in metadata.csv. Skipping.")
        return

    log(f"Found {len(to_transcribe)} files needing transcription (Skipped {len(wav_files) - len(to_transcribe)} existing).")
    pairs = transcribe_files(to_transcribe, progress_callback=progress_callback, model_name="base")

    if not pairs:
        log("No new metadata entries generated.")
        return

    # Merge new pairs with existing
    for k, v in pairs:
        existing[k] = v

    # Sort keys numerically if possible
    def _sort_key(k):
        return (0, int(k)) if k.isdigit() else (1, k)
    
    lines = [f"{k}|{existing[k]}" for k in sorted(existing.keys(), key=_sort_key)]

    # FIX: Use newline='\n' to force Linux line endings for Docker compatibility
    with open(metadata_path, "w", encoding="utf-8", newline='\n') as f:
        f.write("\n".join(lines) + "\n")

    log(f"SUCCESS! Updated metadata.csv with {len(pairs)} new entries (Total: {len(lines)}).")
    log(f"Location: {metadata_path}")
    
    # Validate and fix the metadata file
    is_valid, num_fixes, validation_errors = validate_and_fix_metadata_csv(metadata_path)
    if num_fixes > 0:
        log(f"Metadata validation applied {num_fixes} fix(es)")
    if validation_errors and not is_valid:
        log(f"Metadata validation warnings: {len(validation_errors)} issue(s) found")
        for err in validation_errors[:5]:  # Show first 5 errors
            log(f"  - {err}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python auto_transcribe.py <dataset_folder>")
    else:
        log("Initializing Transcription Worker...")
        transcribe_folder(sys.argv[1])
