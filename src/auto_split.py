import os
import sys
import subprocess
import hashlib
from pathlib import Path

def log(msg):
    print(f"[SPLITTER] {msg}")
    sys.stdout.flush()

def calculate_audio_hash(file_path):
    """Calculate SHA256 hash of an audio file to detect duplicates."""
    sha256 = hashlib.sha256()
    try:
        with open(file_path, 'rb') as f:
            while chunk := f.read(8192):
                sha256.update(chunk)
        return sha256.hexdigest()
    except Exception as e:
        log(f"Warning: Could not hash {file_path}: {e}")
        return None

def remove_duplicate_audio_files(output_folder):
    """Scan output folder and remove duplicate audio files based on SHA256 hash.
    Keeps the first occurrence and deletes duplicates.
    """
    out_path = Path(output_folder)
    if not out_path.exists():
        return 0
    
    log("Checking for duplicate audio files...")
    wav_files = list(out_path.glob("*.wav"))
    
    if len(wav_files) < 2:
        return 0
    
    seen_hashes = {}
    duplicates_removed = 0
    
    for wav_file in wav_files:
        file_hash = calculate_audio_hash(wav_file)
        if not file_hash:
            continue
            
        if file_hash in seen_hashes:
            # Duplicate found - delete it
            original = seen_hashes[file_hash]
            try:
                wav_file.unlink()
                duplicates_removed += 1
                log(f"Removed duplicate: {wav_file.name} (identical to {original})")
            except Exception as e:
                log(f"Warning: Could not remove {wav_file.name}: {e}")
        else:
            # First occurrence - keep it
            seen_hashes[file_hash] = wav_file.name
    
    if duplicates_removed > 0:
        log(f"Removed {duplicates_removed} duplicate audio file(s)")
    else:
        log("No duplicate audio files found")
    
    return duplicates_removed

def ensure_dependencies():
    """Ensure pydub and ffmpeg are installed."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        from pydub import AudioSegment
        from pydub.silence import split_on_silence
    except ImportError:
        log("pydub not found. Installing pydub...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pydub"], creationflags=flags)
    
    # Check for ffmpeg (required by pydub to handle MP3/M4A)
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True, creationflags=flags)
    except (FileNotFoundError, subprocess.CalledProcessError):
        log("WARNING: ffmpeg (audio decoder) not found.")
        if os.name == 'nt':
            log("Attempting to install ffmpeg via winget (requires internet)...")
            try:
                # Gyan.FFmpeg is a reliable community build for Windows
                subprocess.run(
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
                log("ffmpeg installation initiated. You may need to restart the app after it finishes.")
            except Exception as e:
                log(f"Auto-install failed: {e}")
        else:
            log("Please install ffmpeg via your package manager (e.g., sudo apt install ffmpeg)")

def split_master_audio(
    input_file,
    output_folder,
    *,
    min_silence_len: int = 600,
    silence_thresh_offset_db: float = -16,
    keep_silence: int = 250,
):
    ensure_dependencies()
    from pydub import AudioSegment
    from pydub.silence import split_on_silence

    log(f"Loading master file: {input_file}...")
    try:
        audio = AudioSegment.from_file(input_file)
    except Exception as e:
        log(f"Error loading file: {e}")
        return

    log("Splitting audio based on silence (this may take a minute)...")
    # min_silence_len: how long the silence should be (ms)
    # silence_thresh: how quiet it needs to be (dBFS)
    # keep_silence: how much silence to leave at the ends of chunks (ms)
    chunks = split_on_silence(
        audio,
        min_silence_len=int(min_silence_len),
        silence_thresh=float(audio.dBFS) + float(silence_thresh_offset_db),
        keep_silence=int(keep_silence),
    )

    log(f"Found {len(chunks)} speech segments.")
    
    out_path = Path(output_folder)
    out_path.mkdir(parents=True, exist_ok=True)

    from tqdm import tqdm
    print("\nExporting segments:")
    for i, chunk in enumerate(tqdm(chunks, desc="Saving Clips", unit="clip", bar_format="{l_bar}{bar:40}{r_bar}")):
        chunk_name = f"segment_{i+1:03d}.wav"
        chunk_path = out_path / chunk_name
        # Export as 22050Hz Mono (standard for Piper)
        chunk = chunk.set_frame_rate(22050).set_channels(1)
        chunk.export(str(chunk_path), format="wav")
        
        # Keep internal progress for UI listeners
        # print(f"PROGRESS:{i+1}/{len(chunks)}")
        # sys.stdout.flush()

    log(f"SUCCESS! Created {len(chunks)} clips in {output_folder}")
    
    # Remove any duplicate audio segments
    remove_duplicate_audio_files(output_folder)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python auto_split.py <input_wav> <output_folder>")
    else:
        split_master_audio(sys.argv[1], sys.argv[2])
