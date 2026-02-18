import os
import sys
import subprocess
import time
import re
import json
from pathlib import Path
from datetime import datetime

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
    5. Removes lines with severe Whisper hallucinations (multiple ... patterns)
    
    Note: Only removes entries with severe hallucinations to avoid false positives.
    
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
        transcription_text = parts[1].strip() if len(parts) > 1 else ""
        
        # Skip validation if filename looks like a placeholder or comment
        if audio_filename.startswith('#') or not audio_filename:
            continue
        
        # Check 4: Remove lines with triple dots (Whisper hallucinations)
        # ANY occurrence of ... indicates Whisper confusion (silence/noise/hesitation)
        # These create poor training samples, so remove them entirely
        if '...' in transcription_text:
            log(f"WARNING: Removing line {line_num} with ellipsis (likely Whisper confusion): {audio_filename}")
            fixes += 1
            errors.append(f"Line {line_num}: Ellipsis detected ({audio_filename}) - entry removed for better training quality")
            continue
        
        # Check if referenced audio file exists
        # metadata.csv uses format: "filename|text" where filename may or may not have .wav extension
        # WAV files live in dataset/wav/ (sibling "wav" folder relative to metadata.csv location)
        wav_dir = dataset_dir / "wav" if (dataset_dir / "wav").is_dir() else dataset_dir
        if audio_filename.endswith('.wav'):
            audio_path = wav_dir / audio_filename
        else:
            audio_path = wav_dir / f"{audio_filename}.wav"
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

def _ensure_gpu_torch():
    """
    Ensures PyTorch with CUDA support is installed before Whisper is set up.

    Install order:
      1. If NVIDIA GPU is detected (via nvidia-smi), install/reinstall torch with
         CUDA 12.1 support FIRST — before Whisper pulls in the CPU-only build.
      2. If no NVIDIA GPU is found, do nothing (CPU torch is correct).
      3. If torch is already CUDA-capable, skip entirely.

    This guarantees first-time NVIDIA users get GPU acceleration immediately,
    with no wasted double-download of the CPU build.
    """
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        # Fast path: torch already installed and CUDA works — nothing to do.
        import torch
        if torch.cuda.is_available():
            return
        # torch is installed but CUDA unavailable — fall through to GPU check below.
        cpu_only_installed = True
    except ImportError:
        # torch not installed at all yet.
        cpu_only_installed = False

    # Check for an NVIDIA GPU before doing anything.
    try:
        nvidia_present = subprocess.run(
            ["nvidia-smi"],
            capture_output=True,
            creationflags=flags,
        ).returncode == 0
    except Exception:
        nvidia_present = False

    if not nvidia_present:
        return  # No NVIDIA GPU — CPU torch (or no torch) is fine as-is.

    if cpu_only_installed:
        log("NVIDIA GPU detected but PyTorch has no CUDA support (CPU-only build).")
        log("Reinstalling PyTorch with CUDA 12.1 support so Whisper can use your GPU...")
    else:
        log("NVIDIA GPU detected. Installing PyTorch with CUDA 12.1 support before Whisper...")

    try:
        cmd = [
            sys.executable, "-m", "pip", "install",
            "torch",
            "--index-url", "https://download.pytorch.org/whl/cu121",
            "--quiet",
        ]
        if cpu_only_installed:
            cmd.append("--force-reinstall")
        subprocess.check_call(cmd, creationflags=flags)
        log("PyTorch (CUDA) installed successfully. Whisper will now use your GPU.")
    except Exception as e:
        log(f"GPU torch install failed, will fall back to CPU: {e}")


def ensure_dependencies():
    """Ensure whisper and its requirements are installed."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0

    # Before installing Whisper, make sure torch is GPU-capable if possible.
    # This prevents new installs from silently getting the slow CPU-only build.
    _ensure_gpu_torch()

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
    
    # Quality filter counters
    skip_silence = 0
    skip_low_confidence = 0
    skip_hallucination = 0
    skip_errors = 0
    
    # Quality report data - track details for each file
    # Merge with existing report to preserve data from previous runs
    existing_report = {}
    if wav_files:
        report_path = wav_files[0].parent / "transcription_quality_report.json"
        if report_path.exists():
            try:
                with open(report_path, "r", encoding="utf-8") as f:
                    existing_report = json.load(f).get("files", {})
            except Exception:
                pass
    
    quality_report = {
        "timestamp": datetime.now().isoformat(),
        "model": model_name,
        "total_files": total,
        "files": dict(existing_report),  # Start with previous data
        "summary": {}
    }

    log(f"Starting transcription of {total} files...")
    log("Quality filters enabled: silence detection, confidence check, hallucination detection")
    if progress_callback:
        progress_callback(0, total, "Initializing...")

    print()  # Buffer
    for i, wav in enumerate(tqdm(wav_files, desc="Transcribing", unit="file", bar_format="{l_bar}{bar:30}{r_bar}")):
        file_quality = {"filename": wav.name, "status": "error", "reason": None}
        
        try:
            if progress_callback:
                progress_callback(i, total, f"Transcribing {wav.name}")

            result = model.transcribe(str(wav))
            text = (result.get("text") or "").strip()
            
            if text:
                # Quality checks: Use Whisper's confidence metrics to filter out poor samples
                segments = result.get("segments", [])
                if segments:
                    # Calculate average metrics across all segments
                    avg_no_speech = sum(s.get("no_speech_prob", 0) for s in segments) / len(segments)
                    avg_logprob = sum(s.get("avg_logprob", 0) for s in segments) / len(segments)
                    # Compression ratio is also per-segment, calculate average
                    compression = sum(s.get("compression_ratio", 0) for s in segments) / len(segments)
                    
                    # Record quality metrics
                    file_quality["metrics"] = {
                        "no_speech_prob": round(avg_no_speech, 4),
                        "avg_logprob": round(avg_logprob, 4),
                        "compression_ratio": round(compression, 4)
                    }
                    file_quality["text_preview"] = text[:100] + "..." if len(text) > 100 else text
                    file_quality["text_full"] = text  # Full text backup for recovery
                    
                    # Apply quality thresholds
                    if avg_no_speech > 0.6:
                        tqdm.write(f"[SKIP] {wav.name}: Likely silence/noise (no_speech_prob={avg_no_speech:.2f})")
                        log(f"QUALITY FILTER: Skipped {wav.name} - silence/noise detected (no_speech_prob={avg_no_speech:.2f})")
                        file_quality["status"] = "filtered"
                        file_quality["reason"] = "silence/noise"
                        skip_silence += 1
                        quality_report["files"][wav.name] = file_quality
                        continue
                    if avg_logprob < -1.0:
                        tqdm.write(f"[SKIP] {wav.name}: Low confidence transcription (avg_logprob={avg_logprob:.2f})")
                        log(f"QUALITY FILTER: Skipped {wav.name} - low confidence (avg_logprob={avg_logprob:.2f})")
                        file_quality["status"] = "filtered"
                        file_quality["reason"] = "low_confidence"
                        skip_low_confidence += 1
                        quality_report["files"][wav.name] = file_quality
                        continue
                    if compression > 2.4:
                        tqdm.write(f"[SKIP] {wav.name}: Possible hallucination/repetition (compression={compression:.2f})")
                        log(f"QUALITY FILTER: Skipped {wav.name} - hallucination/repetition (compression={compression:.2f})")
                        file_quality["status"] = "filtered"
                        file_quality["reason"] = "hallucination/repetition"
                        skip_hallucination += 1
                        quality_report["files"][wav.name] = file_quality
                        continue
                
                # File passed all quality checks
                file_quality["status"] = "accepted"
                quality_report["files"][wav.name] = file_quality
                results.append((wav.stem, text))
        except Exception as e:
            tqdm.write(f"[ERROR] Transcribing {wav.name}: {e}")
            log(f"ERROR: Failed to transcribe {wav.name}: {e}")
            file_quality["status"] = "error"
            file_quality["reason"] = str(e)
            quality_report["files"][wav.name] = file_quality
            skip_errors += 1

    if progress_callback:
        progress_callback(total, total, "Finalizing...")
    
    # Populate summary in quality report (covers ALL files in report, not just this batch)
    total_skipped = skip_silence + skip_low_confidence + skip_hallucination + skip_errors
    all_files = quality_report["files"]
    all_accepted = sum(1 for f in all_files.values() if f.get("status") == "accepted")
    all_filtered = sum(1 for f in all_files.values() if f.get("status") == "filtered")
    all_errors = sum(1 for f in all_files.values() if f.get("status") == "error")
    all_total = len(all_files)
    quality_report["total_files"] = all_total
    quality_report["summary"] = {
        "total_processed": all_total,
        "accepted": all_accepted,
        "filtered": all_filtered,
        "filtered_silence": skip_silence,
        "filtered_low_confidence": skip_low_confidence,
        "filtered_hallucination": skip_hallucination,
        "errors": all_errors,
        "pass_rate": round(all_accepted / all_total * 100, 1) if all_total > 0 else 0,
        "this_batch": {
            "processed": total,
            "accepted": len(results),
            "filtered": total_skipped
        }
    }
    
    # Save quality report to JSON file in the same folder as the first wav file
    if wav_files:
        report_path = wav_files[0].parent / "transcription_quality_report.json"
        try:
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(quality_report, f, indent=2)
            log(f"Quality report saved: {report_path}")
        except Exception as e:
            log(f"Warning: Could not save quality report: {e}")
    
    # Log quality filter summary to console
    log("=" * 60)
    log("TRANSCRIPTION QUALITY SUMMARY:")
    log(f"  Total files processed: {total}")
    log(f"  Successfully transcribed: {len(results)}")
    log(f"  Filtered out: {total_skipped}")
    if total_skipped > 0:
        log(f"    - Silence/noise: {skip_silence}")
        log(f"    - Low confidence: {skip_low_confidence}")
        log(f"    - Hallucination/repetition: {skip_hallucination}")
        log(f"    - Errors: {skip_errors}")
    log(f"  Quality pass rate: {len(results) / total * 100:.1f}%")
    log("=" * 60)

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
