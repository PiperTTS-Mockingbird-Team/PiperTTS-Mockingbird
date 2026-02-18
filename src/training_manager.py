import os
import sys
import json
import logging
import subprocess
import threading
import time
import re
import shutil
import requests
from pathlib import Path
from typing import List, Dict, Optional, Any

# =============================================================================
# Path Configuration
# =============================================================================

# Root directory of the project (parent of src/)
ROOT_DIR = Path(__file__).resolve().parent.parent

# Location where Piper training "dojos" are stored
# A "dojo" is a bundle containing the dataset, scripts, and logs for a specific voice.
DOJO_ROOT = ROOT_DIR / "training" / "make piper voice models" / "tts_dojo"

# Configure local logger for this module
logger = logging.getLogger(__name__)

# Setup logging with rotation and error aggregation
LOGS_DIR = ROOT_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

error_log_file = LOGS_DIR / "errors.log"

# Add shared error handler if not already present
if not any(isinstance(h, logging.handlers.RotatingFileHandler) and 
           str(getattr(h, 'baseFilename', '')) == str(error_log_file) 
           for h in logger.handlers):
    from logging.handlers import RotatingFileHandler
    detailed_formatter = logging.Formatter("%(asctime)s [%(levelname)s] [%(name)s] %(message)s")
    error_handler = RotatingFileHandler(error_log_file, maxBytes=5*1024*1024, backupCount=3)
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(detailed_formatter)
    logger.addHandler(error_handler)

class TrainingManager:
    """
    Backend manager for Voice Studio (Training dashboard, Slicer, Transcriber).
    Centralizes all logic previously spread across multiple Tkinter UI files.
    
    This class handles:
    - Training process lifecycle (start/stop/monitor)
    - Checkpoint management and auto-saves
    - Thermal and disk space safety monitoring
    - Transcription and dataset slicing tasks
    - Auto-pipeline coordination (hands-off training flow)
    """
    
    def __init__(self):
        # Maps voice_name to tracking threads or process objects
        self._monitoring_threads = {}
        self._training_processes = {}
        self._preprocessing_only_mode = {}  # Track which processes are preprocessing-only (not training)
        
        # Real-time statistics for transcription and dataset filtering
        self._transcription_stats = {} # voice_name -> {current, total, status}
        self._filter_stats = {} # voice_name -> {current, total}
        
        # State tracking for checkpoint monitoring
        self._last_seen_ckpt = {} # voice_name -> filename
        self._session_stats = {} # voice_name -> {start_epoch, first_ckpt_time, ckpts_seen, avg_epoch_time}
        self._ckpt_counters = {} # voice_name -> count since last auto-save
        
        # Operational flags and safety limits
        self._monitor_active = True
        self._gpu_thermal_limit = 85  # Default 85C safety shutoff
        self._thermal_tripped_voices = set()
        self._disk_tripped_voices = set()
        
        # Performance caches to prevent expensive IO on every status poll
        self._wav_stats_cache = {}  # voice_name -> {count, total_ms, mtime}
        self._metadata_cache = {}  # voice_name -> (entries, mtime)

        # Concurrency safety: limit to one transcription task at a time to prevent VRAM overflow
        self._transcription_lock = threading.Semaphore(1)

        # Auto pipeline state (hands-off flow): voice -> {phase, message, started_at, error}
        # phase: idle|transcribing|starting_training|running|done|failed
        self._auto_pipeline_state: Dict[str, Dict[str, Any]] = {}
        self._auto_pipeline_threads: Dict[str, threading.Thread] = {}
        
        # Early Stopping logic based on loss history
        # voice_name -> { history: [], best_avg: float, patience: int }
        self._early_stopping_stats = {} 
        self._early_stopped_voices = set()
        
        # Start a background thread to monitor checkpoints for all dojos globally.
        # This thread runs for the entire lifetime of the TrainingManager instance.
        threading.Thread(target=self._global_monitor_loop, daemon=True).start()

    def _cleanup_training_state(self, voice_name: str, keep_preprocessing_flag: bool = False):
        """Centralized cleanup for training state tracking.
        
        Args:
            voice_name: The voice to clean up
            keep_preprocessing_flag: If True, preserve preprocessing-only mode flag for status checks
        """
        if voice_name in self._training_processes:
            try:
                proc = self._training_processes[voice_name]
                if proc.poll() is None:
                    logger.info(f"Terminating active process for {voice_name}")
                    proc.terminate()
            except Exception as e:
                logger.warning(f"Error terminating process for {voice_name}: {e}")
            del self._training_processes[voice_name]
        
        if not keep_preprocessing_flag and voice_name in self._preprocessing_only_mode:
            del self._preprocessing_only_mode[voice_name]

    def _global_monitor_loop(self):
        """
        Periodically checks all dojos for new checkpoints and handles auto-save/export.
        Also performs safety checks for thermal limits and disk space.
        """
        while self._monitor_active:
            try:
                # 0. Clean up any terminated training processes from our tracker
                for v_name, proc in list(self._training_processes.items()):
                    if proc.poll() is not None:
                        # Keep preprocessing flag temporarily so status checks know the context
                        self._cleanup_training_state(v_name, keep_preprocessing_flag=True)
                        logger.info(f"Monitor: Training process for {v_name} has finished or stopped.")

                # 1. Check GPU Temperature safety across all running training tasks
                self._check_thermal_safety()
                
                # 2. Check Disk Space safety to prevent write errors during training
                self._check_disk_safety()

                # 3. Ensure TensorBoard is running for all active training sessions
                for v_name in list(self._training_processes.keys()):
                    self.ensure_tensorboard(v_name)

                # Iterate through all folders in the DOJO_ROOT to find active/inactive dojos
                if DOJO_ROOT.exists():
                    for item in DOJO_ROOT.iterdir():
                        if item.is_dir() and item.name.endswith("_dojo"):
                            voice_name = item.name.replace("_dojo", "")
                            # Check if the training process has produced a new checkpoint file (.ckpt)
                            self._check_for_new_checkpoints(voice_name)
            except Exception as e:
                logger.error(f"Error in global monitor loop: {e}")
            
            # Wait for 10 seconds before the next sweep
            time.sleep(10) 

    def get_dojo_settings(self, voice_name: str) -> Dict[str, Any]:
        """
        Load voice-specific settings from the dojo directory.
        Looks in:
        1. SETTINGS.txt (numeric/boolean flags)
        2. dataset.conf (gender and language)
        3. .QUALITY (voice quality: Low, Medium, High)
        """
        dojo_path = DOJO_ROOT / f"{voice_name}_dojo"
        settings_file = dojo_path / "scripts" / "SETTINGS.txt"
        conf_path = dojo_path / "dataset" / "dataset.conf"
        q_path = dojo_path / "dataset" / ".QUALITY"
        
        # Default settings used if the respective files are missing or incomplete.
        settings = {
            "PIPER_SAVE_CHECKPOINT_EVERY_N_EPOCHS": 5,
            "AUTO_SAVE_EVERY_NTH_CHECKPOINT_FILE": 10,
            "LIMIT_SAVES_COUNT": 3,
            "ENABLE_AUTO_SAVE": 1,
            "GPU_THERMAL_LIMIT_CELSIUS": 85,
            "MIN_FREE_SPACE_GB": 2,
            "quality": "Medium",
            "gender": "Female",
            "language": "en-us"
        }
        
        # 1. Load numeric settings from SETTINGS.txt (Key=Value format)
        if settings_file.exists():
            try:
                content = settings_file.read_text()
                for line in content.splitlines():
                    if "=" in line:
                        k, v = line.split("=", 1)
                        k_clean = k.strip()
                        if k_clean in settings:
                            try:
                                # Strip comments and extract the integer value
                                v_val = v.split("#")[0].strip()
                                settings[k_clean] = int(v_val)
                            except: pass
            except Exception as e:
                logger.error(f"Error reading settings for {voice_name}: {e}")

        # 2. Load Gender/Language from dataset.conf (accept quoted or unquoted values)
        if conf_path.exists():
            try:
                text = conf_path.read_text(encoding="utf-8")
                # regex to extract DEFAULT_VOICE_TYPE (M/F)
                g_match = re.search(r'^\s*DEFAULT_VOICE_TYPE\s*=\s*["\']?([^"\'\n#]+)["\']?', text, flags=re.MULTILINE)
                if g_match:
                    g_val = g_match.group(1).strip().upper()
                    settings["gender"] = "Male" if g_val in ["M", "MALE"] else "Female"

                # regex to extract ESPEAK_LANGUAGE_IDENTIFIER (e.g. en-us, fr-fr)
                l_match = re.search(r'^\s*ESPEAK_LANGUAGE_IDENTIFIER\s*=\s*["\']?([^"\'\n#]+)["\']?', text, flags=re.MULTILINE)
                if l_match:
                    settings["language"] = l_match.group(1).strip()
            except Exception as e:
                logger.debug(f"Error parsing dataset.conf for {voice_name}: {e}")

        # 3. Load Piper Quality level from the .QUALITY marker file
        if q_path.exists():
            try:
                q_code = q_path.read_text(encoding="utf-8").strip().upper()
                q_map = {"L": "Low", "M": "Medium", "H": "High"}
                settings["quality"] = q_map.get(q_code, "Medium")
            except Exception as e:
                logger.debug(f"Error reading .QUALITY file for {voice_name}: {e}")
        
        return settings

    def delete_dojo(self, voice_name: str) -> Dict[str, Any]:
        """
        Safely deletes a Dojo directory by stopping training first.
        This prevents 'File in use' errors and ensures a clean removal.
        """
        try:
            # 1. Stop training if it is running (signals the container and subprocess)
            self.stop_training(voice_name)
            
            # Wait a moment for Docker/Subprocess to release file handles
            time.sleep(1.5)
            
            # 2. Perform deletion
            dojo_path = DOJO_ROOT / f"{voice_name}_dojo"
            if dojo_path.exists():
                shutil.rmtree(dojo_path)
                logger.info(f"Permanently deleted Dojo: {voice_name}")
                return {"ok": True}
            else:
                return {"ok": False, "error": "Dojo directory not found."}
        except Exception as e:
            logger.error(f"Failed to delete Dojo {voice_name}: {e}")
            return {"ok": False, "error": str(e)}

    def update_dojo_settings(self, voice_name: str, settings: Dict[str, Any]) -> Dict[str, Any]:
        """
        Updates SETTINGS.txt with new values while attempting to preserve original structure/comments.
        This allows the UI to easily sync configuration back to the trainer's text files.
        """
        dojo_path = DOJO_ROOT / f"{voice_name}_dojo"
        settings_file = dojo_path / "scripts" / "SETTINGS.txt"
        
        if not settings_file.exists():
             return {"ok": False, "error": "SETTINGS.txt not found"}

        try:
            content = settings_file.read_text()
            lines = content.splitlines()
            new_lines = []
            updated_keys = set()
            
            for line in lines:
                # Basic check for KEY=VALUE while ignoring lines that are pure comments
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.split("=", 1)
                    k_clean = k.strip()
                    if k_clean in settings:
                        # Re-construct the line while preserving any inline # comments
                        comment = ""
                        if "#" in v:
                            _, comment_part = v.split("#", 1)
                            comment = f" # {comment_part.strip()}"
                        new_lines.append(f"{k_clean}={settings[k_clean]}{comment}")
                        updated_keys.add(k_clean)
                        continue
                new_lines.append(line)
            
            # If any keys were provided that weren't in the original file, append them.
            for k_rem in settings:
                if k_rem not in updated_keys:
                    # Ignore non-numeric keys if they accidentally leak in
                    if isinstance(settings[k_rem], (int, float)):
                        new_lines.append(f"{k_rem}={settings[k_rem]}")
            
            settings_file.write_text("\n".join(new_lines))
            return {"ok": True}
        except Exception as e:
            logger.error(f"Failed to update settings for {voice_name}: {e}")
            return {"ok": False, "error": str(e)}

    def _check_for_new_checkpoints(self, voice_name: str):
        """
        Helper called by the global monitor loop to check if a specific dojo has produced a new .ckpt file.
        Also tracks the training speed (average epoch time) for display in the dashboard.
        """
        dojo_path = DOJO_ROOT / f"{voice_name}_dojo"
        ckpt_dir = dojo_path / "training_folder" / "lightning_logs" / "version_0" / "checkpoints"
        
        if not ckpt_dir.exists():
            return

        try:
            ckpts = list(ckpt_dir.glob("*.ckpt"))
            if not ckpts:
                return

            # The trainer often keeps multiple checkpoints or moves them; we want the most recent one.
            newest = max(ckpts, key=lambda p: p.stat().st_mtime)
            ckpt_name = newest.name
            
            # Only proceed if this is a different checkpoint than the one we recorded previously.
            if self._last_seen_ckpt.get(voice_name) != ckpt_name:
                self._last_seen_ckpt[voice_name] = ckpt_name
                logger.info(f"New checkpoint detected for {voice_name}: {ckpt_name}")
                
                # --- Parity logic: Timing and Auto-Save ---
                settings = self.get_dojo_settings(voice_name)
                
                # Calculate training velocity: how long does an average epoch take?
                try:
                    # Typical Lightning filename format: epoch=5-step=100.ckpt
                    epoch_part = ckpt_name.split('=')[1].split('-')[0]
                    current_epoch = int(epoch_part)
                    now = time.time()
                    
                    if voice_name not in self._session_stats:
                        # Initial baseline for this voice's training session
                        self._session_stats[voice_name] = {
                            "start_epoch": current_epoch,
                            "start_time": now,
                            "ckpts_seen": 0,
                            "avg_epoch_time": 0
                        }
                    else:
                        stats = self._session_stats[voice_name]
                        stats["ckpts_seen"] += 1
                        
                        elapsed = now - stats["start_time"]
                        epochs_done = current_epoch - stats["start_epoch"]
                        
                        if epochs_done > 0:
                            stats["avg_epoch_time"] = elapsed / epochs_done
                except Exception as e:
                    logger.debug(f"Failed to calculate timing for {voice_name}: {e}")

                # If auto-save is enabled, copy the checkpoint to a persistent folder and potentially export it.
                if settings.get("ENABLE_AUTO_SAVE", 1) == 1:
                    threading.Thread(target=self.perform_checkpoint_save, args=(voice_name, newest), daemon=True).start()
                else:
                    logger.info(f"Auto-save is disabled for {voice_name}. Skipping save for {ckpt_name}")
        except Exception as e:
            logger.error(f"Error checking checkpoints for {voice_name}: {e}")

    def perform_checkpoint_save(self, voice_name: str, ckpt_path: Path):
        """
        Safeguards the latest training progress by copying it to the 'voice_checkpoints' folder.
        Also enforces storage limits to prevent the drive from filling up with hundreds of GBs of old models.
        """
        dojo_path = DOJO_ROOT / f"{voice_name}_dojo"
        save_dir = dojo_path / "voice_checkpoints"
        voices_dir = dojo_path / "tts_voices"
        filename = ckpt_path.name
        target = save_dir / filename
        
        # Avoid redundant work if we've already saved this exact file.
        if target.exists():
            return

        try:
            save_dir.mkdir(exist_ok=True)
            
            # --- Safety check: Wait for file to finish writing ---
            # Python script might see the file before Docker is done writing the last bytes.
            last_size = -1
            max_wait = 30 # wait up to 60 seconds (check every 2s)
            waited = 0
            while waited < max_wait:
                current_size = ckpt_path.stat().st_size
                if current_size == last_size and current_size > 0:
                    break
                last_size = current_size
                time.sleep(2)
                waited += 1

            # --- CHECKPOINT ZIP VALIDATION ---
            # PyTorch checkpoints are zip files. Validate before saving to prevent
            # "PytorchStreamReader failed reading zip archive" errors on resume.
            import zipfile
            try:
                with zipfile.ZipFile(ckpt_path, 'r') as zf:
                    # Quick integrity check - list contents without extracting
                    _ = zf.namelist()
                logger.debug(f"Checkpoint {filename} passed zip validation")
            except (zipfile.BadZipFile, Exception) as e:
                logger.error(f"Checkpoint validation FAILED for {filename}: {e}")
                logger.warning(f"Skipping save of corrupted checkpoint. Training will continue.")
                return  # Abort save - don't copy corrupt file

            # Perform atomic copy: Copy to a temporary file first, then rename.
            # This prevents half-written or corrupt models if the server crashes during copy.
            temp_target = target.with_suffix(".tmp")
            shutil.copy2(ckpt_path, temp_target)
            os.replace(temp_target, target)
            
            logger.info(f"Successfully saved {filename} to voice_checkpoints for {voice_name}")
            
            # --- STORAGE MANAGEMENT ---
            # Automatically delete the oldest models if we've exceeded the 'keep' limit.
            settings = self.get_dojo_settings(voice_name)
            keep = max(1, settings.get("LIMIT_SAVES_COUNT", 3))
            
            # Identify the BEST quality model so we can protect it from deletion
            best_mel_loss = float('inf')
            best_voice_folder = None
            best_epoch_str = None
            
            if voices_dir.exists():
                # Scan for .mel_loss metadata files to find the lowest value
                for p in voices_dir.glob("**/*.onnx.mel_loss"):
                    try:
                        val = float(p.read_text().strip())
                        if val < best_mel_loss:
                            best_mel_loss = val
                            best_voice_folder = p.parent
                            # Extract epoch from ONNX filename (e.g. en_US-voice_2344-medium.onnx)
                            # Expected pattern: _(\d+)- or -(\d+)-
                            m = re.search(r"_(\d+)-", p.name)
                            if m:
                                best_epoch_str = m.group(1)
                    except Exception as e:
                        logger.debug(f"Error reading mel_loss file {p}: {e}")

            # 1. Cleanup old .ckpt files
            all_ckpts = sorted(list(save_dir.glob("*.ckpt")), key=lambda p: p.stat().st_mtime, reverse=True)
            if len(all_ckpts) > keep:
                to_delete = all_ckpts[keep:]
                for old_ckpt in to_delete:
                    # PROTECTION: Skip if this is the best checkpoint
                    if best_epoch_str and f"epoch={best_epoch_str}" in old_ckpt.name:
                        logger.info(f"Storage cleanup: PROTECTING best quality checkpoint {old_ckpt.name} (Loss: {best_mel_loss})")
                        continue

                    try:
                        old_ckpt.unlink()
                        logger.info(f"Storage cleanup: Deleted old checkpoint {old_ckpt.name}")
                    except Exception as e:
                        logger.warning(f"Failed to delete checkpoint {old_ckpt.name}: {e}")
            
            # 2. Cleanup old .onnx voice folders
            if voices_dir.exists():
                all_voices = sorted(
                    [d for d in voices_dir.iterdir() if d.is_dir() and d.name != ".required_directory"],
                    key=lambda d: d.stat().st_mtime,
                    reverse=True
                )
                if len(all_voices) > keep:
                    to_delete_voices = all_voices[keep:]
                    for old_folder in to_delete_voices:
                        # PROTECTION: Skip if this folder contains the best ONNX model
                        if best_voice_folder and old_folder.name == best_voice_folder.name:
                            logger.info(f"Storage cleanup: PROTECTING best quality voice folder {old_folder.name}")
                            continue

                        try:
                            shutil.rmtree(old_folder)
                            logger.info(f"Storage cleanup: Deleted old voice folder {old_folder.name}")
                        except Exception as e:
                            logger.warning(f"Failed to delete voice folder {old_folder.name}: {e}")
            
            # --- AUTO-EXPORT ---
            # Triggers logic to convert this checkpoint to .onnx and move it to production.
            self.trigger_export(voice_name, filename)
                
        except Exception as e:
            logger.error(f"Error performing save for {voice_name}: {e}")

    def export_to_production(self, voice_name: str, onnx_filename: str) -> Dict[str, Any]:
        """
        Copies a finished model (.onnx) and its config (.onnx.json) from the training folder
        into the live 'voices/custom' directory used by the Piper TTS server.
        """
        dojo_path = DOJO_ROOT / f"{voice_name}_dojo"
        voices_dir = dojo_path / "tts_voices"
        
        # Traverse the local voices folder to find the requested .onnx file.
        onnx_path = None
        for p in voices_dir.glob(f"**/{onnx_filename}"):
            onnx_path = p
            break
            
        if not onnx_path or not onnx_path.exists():
            return {"ok": False, "error": f"Model file {onnx_filename} not found in tts_voices"}
            
        # Piper requires both the .onnx file and a matching .json configuration file.
        # We check for .onnx.json or just .json depending on how it was named.
        json_path = onnx_path.with_suffix(onnx_path.suffix + ".json")
        if not json_path.exists():
            json_path = onnx_path.with_suffix(".onnx.json")

        if not json_path.exists():
            return {"ok": False, "error": "Missing model config (.onnx.json)."}

        # Define destination: voices/custom/<voice_name>/
        dest_dir = ROOT_DIR / "voices" / "custom" / voice_name
        dest_dir.mkdir(parents=True, exist_ok=True)

        dest_onnx = dest_dir / onnx_path.name
        dest_json = dest_dir / json_path.name

        try:
            # Perform atomic-like copies of the model and its metadata
            shutil.copy2(onnx_path, dest_onnx)
            shutil.copy2(json_path, dest_json)
            
            # Optional: Automatic update of the main server config to use this new voice as default.
            cfg_path = ROOT_DIR / "src" / "config.json"
            if cfg_path.exists():
                try:
                    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
                    cfg["voice_model"] = dest_onnx.name
                    cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
                except: pass
                
            # Attempt to notify the running Piper Server to reload its voice cache
            try:
                import urllib.request
                url = "http://localhost:5000/api/reload-voices" # Default port for the local server
                req = urllib.request.Request(url, method="POST", data=b"{}", headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=2) as resp:
                    pass
            except: pass

            return {"ok": True, "path": str(dest_onnx)}
        except Exception as e:
            logger.error(f"Production export failed for {voice_name}: {e}")
            return {"ok": False, "error": str(e)}

    def list_dojos(self) -> List[Dict[str, Any]]:
        """
        Scans the DOJO_ROOT for all existing training environments.
        Returns a list of metadata dictionaries used for the UI dashboard.
        """
        dojos = []
        if not DOJO_ROOT.exists():
            return []

        # List all directories ending in _dojo, ignoring internal system folders.
        for item in DOJO_ROOT.iterdir():
            if item.is_dir() and item.name.endswith("_dojo") and item.name != "DOJO_CONTENTS":
                dojo_info = self.get_dojo_info(item.name.replace("_dojo", ""))
                if dojo_info:
                    dojos.append(dojo_info)
        
        # Sort alphabetically for consistent UI listing
        dojos.sort(key=lambda x: x["name"])
        return dojos

    def get_dojo_info(self, voice_name: str) -> Optional[Dict[str, Any]]:
        """
        Gathers health and status information about a specific voice training environment.
        Checks quality settings, dataset volume, and file integrity.
        """
        dojo_path = DOJO_ROOT / f"{voice_name}_dojo"
        if not dojo_path.exists():
            return None

        # Determine Quality level from marker file
        quality = "Unknown"
        quality_file = dojo_path / "dataset" / ".QUALITY"
        if quality_file.exists():
            quality = quality_file.read_text().strip()

        # Calculate Dataset Volume (total bytes of raw audio files)
        dataset_path = dojo_path / "dataset" / "wav"
        dataset_size = 0
        if dataset_path.exists():
            for f in dataset_path.glob("*.wav"):
                dataset_size += f.stat().st_size

        # Calculate Total Storage (entire dojo directory)
        total_size = 0
        try:
            for item in dojo_path.rglob("*"):
                if item.is_file():
                    total_size += item.stat().st_size
        except Exception as e:
            logger.warning(f"Could not calculate total size for {voice_name}: {e}")

        return {
            "name": voice_name,
            "path": str(dojo_path),
            "quality": quality,
            "dataset_size": dataset_size,
            "total_size": total_size,
            "is_training": False, # Status checked dynamically elsewhere via Docker/Processes
            "has_metadata": (dojo_path / "dataset" / "metadata.csv").exists(),
            "last_modified": dojo_path.stat().st_mtime
        }

    def create_dojo(self, voice_name: str, quality: str = "M", gender: str = "F", scratch: bool = False) -> Dict[str, Any]:
        """
        Initializes a brand-new training environment by calling the 'new_dojo.ps1' PowerShell script.
        """
        script_path = ROOT_DIR / "training" / "make piper voice models" / "new_dojo.ps1"
        if not script_path.exists():
            raise FileNotFoundError(f"new_dojo.ps1 not found at {script_path}")

        training_dir = ROOT_DIR / "training" / "make piper voice models"
        
        # Construct the execution command for PowerShell
        cmd = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-Command", f"./new_dojo.ps1 -VoiceName '{voice_name}' -Quality '{quality}' -Gender '{gender}' -Scratch '{str(scratch).lower()}'"
        ]

        logger.info(f"Creating dojo: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            cwd=str(training_dir),
            capture_output=True,
            text=True,
            # Prevent popup windows from breaking focus on Windows
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        
        if result.returncode != 0:
            logger.error(f"Dojo creation failed: {result.stderr}")
            return {"ok": False, "error": result.stderr}

        return {"ok": True, "info": self.get_dojo_info(voice_name)}

    def update_dataset_settings(self, voice_name: str, settings: Dict[str, str]) -> Dict[str, Any]:
        """
        Syncs UI-provided dataset parameters back to internal configuration files.
        Typically used to change gender or language of a dataset before starting training.
        """
        dojo_path = DOJO_ROOT / f"{voice_name}_dojo"
        conf_paths = [
            dojo_path / "dataset" / "dataset.conf",
            dojo_path / "target_voice_dataset" / "dataset.conf",
        ]
        q_paths = [
            dojo_path / "dataset" / ".QUALITY",
            dojo_path / "target_voice_dataset" / ".QUALITY",
        ]

        if not dojo_path.exists():
            return {"ok": False, "error": f"Dojo {voice_name} not found"}

        try:
            # 1. Update BOTH dataset.conf copies (dataset + target_voice_dataset)
            for conf_path in conf_paths:
                if not conf_path.exists():
                    continue

                text = conf_path.read_text(encoding="utf-8")

                if "gender" in settings:
                    g_code = "M" if str(settings["gender"]).upper() in ["MALE", "M"] else "F"
                    # Use re.compile for compatibility with Python < 3.11 when using flags
                    pattern = re.compile(r'^\s*DEFAULT_VOICE_TYPE\s*=.*$', flags=re.MULTILINE)
                    if pattern.search(text):
                        text = pattern.sub(f'DEFAULT_VOICE_TYPE="{g_code}"', text)
                    else:
                        text = text.rstrip("\r\n") + f"\nDEFAULT_VOICE_TYPE=\"{g_code}\"\n"

                if "language" in settings:
                    l_code = str(settings["language"]).strip().lower()
                    pattern = re.compile(r'^\s*ESPEAK_LANGUAGE_IDENTIFIER\s*=.*$', flags=re.MULTILINE)
                    if pattern.search(text):
                        text = pattern.sub(f'ESPEAK_LANGUAGE_IDENTIFIER="{l_code}"', text)
                    else:
                        text = text.rstrip("\r\n") + f"\nESPEAK_LANGUAGE_IDENTIFIER=\"{l_code}\"\n"

                conf_path.write_text(text, encoding="utf-8")

            # 2. Update .QUALITY in BOTH dataset + target_voice_dataset
            if "quality" in settings:
                q_map = {"LOW": "L", "MEDIUM": "M", "HIGH": "H"}
                q_code = q_map.get(str(settings["quality"]).upper(), "M")
                for qp in q_paths:
                    qp.parent.mkdir(parents=True, exist_ok=True)
                    qp.write_text(q_code + "\n", encoding="utf-8")

            return {"ok": True}
        except Exception as e:
            logger.error(f"Failed to update dojo settings: {e}")
            return {"ok": False, "error": str(e)}

    def get_dataset_stats(self, voice_name: str) -> Dict[str, Any]:
        """
        Calculates the total duration and total number of audio samples in a voice's dataset.
        Uses aggressive caching to avoid expensive wav file scans on every UI poll.
        """
        dojo_path = DOJO_ROOT / f"{voice_name}_dojo"
        wav_path = dojo_path / "dataset" / "wav"
        metadata_path = dojo_path / "dataset" / "metadata.csv"
        
        # Check if metadata file has changed (only rescan if it has)
        metadata_mtime = 0
        if metadata_path.exists():
            try:
                metadata_mtime = metadata_path.stat().st_mtime
            except:
                pass
        
        # Use cached wav stats if metadata hasn't changed
        total_ms = 0
        total_count = 0
        cached = self._wav_stats_cache.get(voice_name)
        
        if cached and cached.get("mtime") == metadata_mtime:
            # Cache hit - reuse previous scan results
            total_ms = cached["total_ms"]
            total_count = cached["count"]
        else:
            # Cache miss or stale - rescan wav files
            if wav_path.exists():
                import wave
                for f in wav_path.glob("*.wav"):
                    try:
                        with wave.open(str(f), 'rb') as wav:
                            frames = wav.getnframes()
                            rate = wav.getframerate()
                            duration = (frames / float(rate)) * 1000
                            total_ms += int(duration)
                            total_count += 1
                    except Exception as e:
                        logger.debug(f"Error reading wav file {f.name}: {e}")
            
            # Update cache
            self._wav_stats_cache[voice_name] = {
                "total_ms": total_ms,
                "count": total_count,
                "mtime": metadata_mtime
            }
        
        # Check preprocessing status (dataset.jsonl)
        training_folder = dojo_path / "training_folder"
        dataset_jsonl = training_folder / "dataset.jsonl"
        
        preprocessed_count = 0
        is_stale = False
        
        if dataset_jsonl.exists():
            try:
                # Force file sync to ensure we read the latest data
                dataset_jsonl.stat()  # Refresh filesystem cache
                with open(dataset_jsonl, "r", encoding="utf-8", errors="ignore") as f:
                    preprocessed_count = sum(1 for _ in f)
            except:
                pass
        
        # Get metadata count (uses cached version if available)
        meta_count = 0
        if metadata_path.exists():
            try:
                meta_entries = self.get_metadata(voice_name)
                meta_count = len([e for e in meta_entries if e.get("id")])
            except:
                pass
        
        if preprocessed_count != meta_count and meta_count > 0:
            is_stale = True
        
        logger.debug(f"Dataset stats for {voice_name}: preprocessed={preprocessed_count}, meta={meta_count}, is_stale={is_stale}, is_preprocessed={(preprocessed_count > 0 and not is_stale)}")

        return {
            "total_ms": total_ms,
            "count": total_count,
            "total_duration_pretty": self._format_ms(total_ms),
            "preprocessed_count": preprocessed_count,
            "is_preprocessed": (preprocessed_count > 0 and not is_stale),
            "is_stale": is_stale,
            "meta_count": meta_count
        }

    def _format_ms(self, ms: int) -> str:
        """Helper to convert milliseconds into a human-readable HH:MM:SS string."""
        s = ms // 1000
        m = s // 60
        h = m // 60
        return f"{h}h {m % 60}m {s % 60}s" if h > 0 else f"{m}m {s % 60}s"

    def get_audio_files(self, voice_name: str) -> List[Dict[str, Any]]:
        """
        Returns a list of all raw audio files currently in the dataset.
        Includes basic file metadata (size, modification time).
        """
        dojo_path = DOJO_ROOT / f"{voice_name}_dojo"
        wav_path = dojo_path / "dataset" / "wav"
        
        files = []
        if wav_path.exists():
            for f in wav_path.glob("*.wav"):
                files.append({
                    "name": f.name,
                    "size": f.stat().st_size,
                    "mtime": f.stat().st_mtime
                })
        
        # Sort alphabetically by filename
        files.sort(key=lambda x: x["name"])
        return files

    def run_auto_split(
        self,
        voice_name: str,
        master_file_path: str,
        *,
        min_silence_len_ms: int = 600,
        silence_thresh_offset_db: float = -16.0,
        keep_silence_ms: int = 250,
    ) -> Dict[str, Any]:
        """
        Automatically slices a long 'master' audio file into small training clips
        based on silence detection using pydub.
        Clips are saved directly to the dojo's dataset/wav folder.
        """
        dojo_path = DOJO_ROOT / f"{voice_name}_dojo"
        output_folder = dojo_path / "dataset" / "wav"
        raw_folder = dojo_path / "dataset" / "raw"
        
        # Ensure target directories exist before processing
        if not output_folder.exists():
            output_folder.mkdir(parents=True)
        if not raw_folder.exists():
            raw_folder.mkdir(parents=True)

        # Archive a copy of the original master file for later reference or re-slicing.
        master_dest = raw_folder / "master.wav"
        if master_file_path != str(master_dest):
            shutil.copy2(master_file_path, str(master_dest))

        from auto_split import split_master_audio
        
        try:
            # Perform the automated slicing operation.
            # This is a CPU-intensive task that might take a few seconds depending on file length.
            split_master_audio(
                str(master_dest),
                str(output_folder),
                min_silence_len=int(min_silence_len_ms),
                silence_thresh_offset_db=float(silence_thresh_offset_db),
                keep_silence=int(keep_silence_ms),
            )
            return {"ok": True, "count": len(list(output_folder.glob("*.wav")))}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def detect_nonsilent_segments(
        self,
        voice_name: str,
        master_file_path: str,
        *,
        min_silence_len_ms: int = 300,
        silence_thresh_offset_db: float = -16.0,
        pad_ms: int = 200,
        min_segment_ms: int = 500,
    ) -> Dict[str, Any]:
        """
        Scans a master audio file and identifies non-silent regions WITHOUT exporting them yet.
        Returns a list of timestamp ranges [start, end] so the UI can preview the cuts.
        """

        dojo_path = DOJO_ROOT / f"{voice_name}_dojo"
        raw_folder = dojo_path / "dataset" / "raw"
        raw_folder.mkdir(parents=True, exist_ok=True)

        # Ensure the master file is staged in the dojo's raw folder.
        master_dest = raw_folder / "master.wav"
        if master_file_path != str(master_dest):
            shutil.copy2(master_file_path, str(master_dest))

        try:
            from pydub import AudioSegment
            from pydub.silence import detect_nonsilent

            # Load the audio and calculate the volume-based silence threshold
            audio = AudioSegment.from_file(str(master_dest))
            db_thresh = float(audio.dBFS) + float(silence_thresh_offset_db)

            # Analyze the file for speech segments
            ranges = detect_nonsilent(
                audio,
                min_silence_len=int(min_silence_len_ms),
                silence_thresh=db_thresh,
                seek_step=5,
            )

            segments: list[dict[str, int]] = []
            dur_ms = int(len(audio))
            for start, end in ranges:
                # Add padding to ensure speech isn't clipped too closely
                start = max(0, int(start) - int(pad_ms))
                end = min(dur_ms, int(end) + int(pad_ms))
                
                # Filter out segments that are too short to be useful training data
                if (end - start) < int(min_segment_ms):
                    continue
                segments.append({"start_ms": start, "end_ms": end})

            return {"ok": True, "segments": segments}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_master_audio_info(self, voice_name: str) -> Dict[str, Any]:
        """
        Retrieves status of the original (un-sliced) master audio file if it exists.
        Returns the logical path for use in the UI and file size.
        """
        dojo_path = DOJO_ROOT / f"{voice_name}_dojo"
        master_path = dojo_path / "dataset" / "raw" / "master.wav"
        
        if master_path.exists():
            return {
                "exists": True,
                # Logical URI mapping for the web server
                "path": f"/dojo_data/{voice_name}_dojo/dataset/raw/master.wav",
                "size": master_path.stat().st_size
            }
        return {"exists": False}

    def export_segment(
        self,
        voice_name: str,
        start_ms: int,
        end_ms: int,
        segment_name: str,
        naming_mode: str = "ui",
    ) -> Dict[str, Any]:
        """
        Cuts a specific segment out of the master audio file and saves it as a training clip.
        Handles both custom naming (e.g. from UI tags) and automatic numeric sequencing.
        """
        dojo_path = DOJO_ROOT / f"{voice_name}_dojo"
        master_path = dojo_path / "dataset" / "raw" / "master.wav"
        output_folder = dojo_path / "dataset" / "wav"
        
        if not master_path.exists():
            return {"ok": False, "error": "Master audio not found"}
        
        output_folder.mkdir(parents=True, exist_ok=True)

        mode = (naming_mode or "ui").strip().lower()

        def _next_numeric_wav_name() -> str:
            """Finds the next available integer-named file (e.g. 1.wav, 2.wav)."""
            max_n = 0
            try:
                for p in output_folder.glob("*.wav"):
                    stem = p.stem
                    if stem.isdigit():
                        max_n = max(max_n, int(stem))
            except Exception:
                pass
            n = max_n + 1
            # Check for collisions with files that might have been skipped.
            while (output_folder / f"{n}.wav").exists():
                n += 1
            return f"{n}.wav"

        # Determine the target filename based on the naming mode.
        if mode == "numeric":
            name = _next_numeric_wav_name()
        else:
            name = (segment_name or "").strip()
            if not name:
                name = "segment_001.wav"
            if not name.lower().endswith(".wav"):
                name = name + ".wav"

            # Check for collisions and add numeric suffix if name is already taken.
            dest_path = output_folder / name
            if dest_path.exists():
                stem = dest_path.stem
                suffix = dest_path.suffix
                n = 1
                while True:
                    candidate = output_folder / f"{stem}_{n:03d}{suffix}"
                    if not candidate.exists():
                        dest_path = candidate
                        name = candidate.name
                        break
                    n += 1

        dest_path = output_folder / name

        try:
            from pydub import AudioSegment
            audio = AudioSegment.from_file(str(master_path))
            chunk = audio[start_ms:end_ms]
            
            # PIPER Standard: Audio must be 22050Hz Mono for best compatibility.
            chunk = chunk.set_frame_rate(22050).set_channels(1)
            chunk.export(str(dest_path), format="wav")
            return {"ok": True, "path": name}
        except Exception as e:
            logger.error(f"Failed to export segment {name}: {e}")
            return {"ok": False, "error": str(e)}

    def run_transcription(self, voice_name: str, wav_ids: Optional[List[str]] = None, *, replace_existing: bool = True) -> Dict[str, Any]:
        """
        Runs automated text-to-speech transcription using Whisper AI.
        Can process all audio files in the dataset or a specific subset.
        Updates metadata.csv with the results.
        """
        dojo_path = DOJO_ROOT / f"{voice_name}_dojo"
        dataset_path = dojo_path / "dataset"
        wav_folder = dataset_path / "wav"
        metadata_path = dataset_path / "metadata.csv"

        from auto_transcribe import transcribe_files
        
        def update_progress(current, total, status):
            """Internal callback so the transcribe process can report progress via the UI."""
            self._transcription_stats[voice_name] = {
                "current": current,
                "total": total,
                "status": status
            }

        try:
            update_progress(0, 1, "Loading Whisper AI...")

            if not wav_folder.exists():
                raise RuntimeError(f"WAV folder not found: {wav_folder}")

            # Load the current metadata to avoid re-transcribing files that already have text (unless replace_existing is True)
            existing = {}
            for e in self.get_metadata(voice_name):
                _id = (e.get("id") or "").strip()
                if _id:
                    existing[_id] = e.get("text") or ""

            if wav_ids is None:
                # Standard Mode: Transcribe every file in the 'wav' folder.
                # Check quality report to see which files have already been quality-checked.
                # Only skip files that have BOTH a metadata entry AND a quality report entry.
                all_wavs = list(wav_folder.glob("*.wav"))
                
                # Load existing quality report to check which files were quality-filtered
                quality_report_path = wav_folder / "transcription_quality_report.json"
                quality_checked = set()
                if quality_report_path.exists():
                    try:
                        import json
                        with open(quality_report_path, "r", encoding="utf-8") as qf:
                            qr = json.load(qf)
                            quality_checked = set(qr.get("files", {}).keys())
                    except Exception:
                        pass
                
                wav_paths = []
                for wp in all_wavs:
                    has_metadata = wp.stem in existing and existing[wp.stem].strip()
                    has_quality = f"{wp.stem}.wav" in quality_checked or wp.name in quality_checked
                    # Skip ONLY if file has both metadata AND quality report entry
                    if has_metadata and has_quality:
                        continue
                    wav_paths.append(wp)
                
                if not wav_paths:
                    return {"ok": True, "message": "All files already transcribed."}
            else:
                # Manual Mode: Transcribe only specific files requested by ID.
                wanted = {str(x).strip() for x in wav_ids if str(x).strip()}
                wav_paths = [wav_folder / f"{wid}.wav" for wid in wanted]

            # Invoke Whisper (running locally on CPU or GPU if available)
            # We use a semaphore lock to prevent multiple simultaneous Whisper runs 
            # from crashing the GPU (VRAM overflow).
            update_progress(0, 1, "Waiting for previous transcription task to finish...")
            with self._transcription_lock:
                update_progress(0, 1, "Loading Whisper AI...")
                pairs = transcribe_files(wav_paths, progress_callback=update_progress, model_name="base")

            # Merge results back into the metadata map
            for _id, text in pairs:
                if replace_existing or (_id not in existing) or (not (existing.get(_id) or "").strip()):
                    existing[_id] = text

            # Write the metadata.csv file in the Piper-standard format: ID|TEXT\n
            # Sort keys numerically if possible for better human readability.
            def _sort_key(k: str):
                return (0, int(k)) if k.isdigit() else (1, k)

            lines = [f"{k}|{existing[k]}" for k in sorted(existing.keys(), key=_sort_key)]
            metadata_path.parent.mkdir(parents=True, exist_ok=True)
            with open(metadata_path, "w", encoding="utf-8", newline="\n") as f:
                f.write("\n".join(lines) + ("\n" if lines else ""))
            
            # Run validation on the FULL metadata to remove ellipsis and bad entries
            # This catches entries from ALL transcription runs, not just the current batch
            try:
                from auto_transcribe import validate_and_fix_metadata_csv
                is_valid, num_fixes, val_errors = validate_and_fix_metadata_csv(metadata_path)
                if num_fixes > 0:
                    logger.info(f"Post-transcription validation applied {num_fixes} fix(es) for {voice_name}")
            except Exception as e:
                logger.error(f"Post-transcription validation failed: {e}")
            
            # Clear logical stats so the progress bar disappears from the UI.
            if voice_name in self._transcription_stats:
                del self._transcription_stats[voice_name]
                
            return {"ok": True}
        except Exception as e:
            logger.error(f"Transcription failed for {voice_name}: {e}")
            if voice_name in self._transcription_stats:
                del self._transcription_stats[voice_name]
            return {"ok": False, "error": str(e)}

    def get_transcription_progress(self, voice_name: str) -> Optional[Dict[str, Any]]:
        """Returns the current progress (current/total/status) of a Whispering task."""
        return self._transcription_stats.get(voice_name)

    def run_preprocessing(self, voice_name: str) -> Dict[str, Any]:
        """
        Manually trigger Piper preprocessing (feature extraction) without starting training.
        Uses the run_training.ps1 script with -PreprocessOnly flag.
        """
        dojo_name = f"{voice_name}_dojo"
        script_dir = ROOT_DIR / "training" / "make piper voice models"
        
        # Verify dojo exists
        if not (DOJO_ROOT / dojo_name).exists():
            return {"ok": False, "error": f"Dojo {dojo_name} not found."}

        # Check if already running
        if voice_name in self._training_processes:
            return {"ok": False, "error": "Training or Preprocessing is already active for this voice."}

        log_file = DOJO_ROOT / dojo_name / "training_log.txt"
        log_file.parent.mkdir(parents=True, exist_ok=True)

        # Ensure marker files and configuration are synced before starting preprocessing
        try:
            current_settings = self.get_dojo_settings(voice_name)
            self.generate_configs(
                voice_name, 
                quality=current_settings.get("quality", "Medium"),
                gender=current_settings.get("gender", "Female"),
                language=current_settings.get("language", "en-us")
            )
        except Exception as e:
            logger.error(f"Config generation failed during preprocessing prep: {e}")

        # ── Pre-preprocessing: validate metadata and purge stale cache ──────
        dojo_path = DOJO_ROOT / dojo_name
        dataset_path = dojo_path / "dataset"
        metadata_path = dataset_path / "metadata.csv"
        training_folder = dojo_path / "training_folder"
        dataset_jsonl = training_folder / "dataset.jsonl"

        # 1) Run metadata validation (removes ellipsis entries, blank lines, etc.)
        if metadata_path.exists():
            try:
                from auto_transcribe import validate_and_fix_metadata_csv
                is_valid, num_fixes, validation_errors = validate_and_fix_metadata_csv(metadata_path)
                if num_fixes > 0:
                    logger.info(f"Pre-preprocessing validation applied {num_fixes} fix(es) for {voice_name}")
            except Exception as e:
                logger.error(f"Metadata validation failed: {e}")

        # 2) Purge stale preprocessing cache so Docker will re-preprocess
        #    If dataset.jsonl exists but metadata count changed, or if we just
        #    fixed metadata, the old cache is invalid.
        if dataset_jsonl.exists():
            try:
                meta_count = 0
                if metadata_path.exists():
                    with open(metadata_path, 'r', encoding='utf-8') as f:
                        meta_count = sum(1 for line in f if line.strip())
                jsonl_count = 0
                with open(dataset_jsonl, 'r', encoding='utf-8') as f:
                    jsonl_count = sum(1 for _ in f)
                if jsonl_count != meta_count:
                    logger.info(
                        f"Stale preprocessing cache for {voice_name}: "
                        f"dataset.jsonl={jsonl_count} vs metadata.csv={meta_count}. Purging."
                    )
                    # Purge cache, config.json and dataset.jsonl
                    shutil.rmtree(training_folder / "cache", ignore_errors=True)
                    for p in (training_folder / "config.json", dataset_jsonl):
                        try:
                            if p.exists():
                                p.unlink()
                        except Exception:
                            pass
            except Exception as e:
                logger.error(f"Cache invalidation check failed: {e}")

        # Construct PS command for PREPROCESS ONLY
        ps_command = f"Set-Location -Path '{script_dir}'; ./run_training.ps1 -SelectedDojo '{dojo_name}' -Auto:$true -PreprocessOnly:$true *>&1 | Tee-Object -FilePath '{log_file}'"

        cmd = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            ps_command,
        ]

        try:
            logger.info(f"Launching Manual Preprocessing: {cmd}")
            proc = subprocess.Popen(
                cmd,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                stdin=subprocess.PIPE,
                stdout=None,
                stderr=None,
                text=True,
                bufsize=1,
            )
            self._training_processes[voice_name] = proc
            self._preprocessing_only_mode[voice_name] = True  # Mark as preprocessing-only
            return {"ok": True}
        except Exception as e:
            logger.error(f"Failed to launch manual preprocessing: {e}")
            return {"ok": False, "error": str(e)}

    def set_filter_progress(self, voice_name: str, current: int, total: int):
        """Sets external status for dataset filtering logic (e.g. check for bad audio)."""
        self._filter_stats[voice_name] = {"current": current, "total": total}

    def get_filter_progress(self, voice_name: str) -> Optional[Dict[str, Any]]:
        """Returns the numeric progress of an ongoing dataset filter task."""
        return self._filter_stats.get(voice_name)

    def clear_filter_progress(self, voice_name: str):
        """Removes progress tracking for a completed filter task."""
        if voice_name in self._filter_stats:
            del self._filter_stats[voice_name]

    def get_metadata(self, voice_name: str) -> List[Dict[str, str]]:
        """
        Parses a dojo's 'metadata.csv' file with intelligent caching.
        Returns a list of dictionaries with 'id' (filename without .wav) and 'text' (transcription).
        Ensures consistent numeric sorting for use in the UI.
        """
        metadata_path = DOJO_ROOT / f"{voice_name}_dojo" / "dataset" / "metadata.csv"
        if not metadata_path.exists():
            return []
        
        # Check cache validity based on file modification time
        try:
            current_mtime = metadata_path.stat().st_mtime
            cached_data = self._metadata_cache.get(voice_name)
            
            if cached_data and cached_data[1] == current_mtime:
                # Cache hit - return cached entries
                return cached_data[0]
        except:
            pass

        # Cache miss - parse the file
        entries = []
        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                for line in f:
                    if "|" in line:
                        parts = line.strip().split("|", 1)
                        if len(parts) == 2:
                            entries.append({"id": parts[0], "text": parts[1]})
        except Exception as e:
            logger.error(f"Error reading metadata: {e}")
            
        # Sort numerically by ID
        def numeric_key(entry):
            id_val = entry.get('id', '')
            return int(id_val) if id_val.isdigit() else id_val
            
        entries.sort(key=numeric_key)
        
        # Update cache
        try:
            current_mtime = metadata_path.stat().st_mtime
            self._metadata_cache[voice_name] = (entries, current_mtime)
        except:
            pass
        
        return entries

    def save_metadata(self, voice_name: str, entries: List[Dict[str, str]]) -> bool:
        """
        Writes the provided metadata entries back to the dojo's metadata.csv.
        Automatically sorts entries numerically before saving to maintain file order.
        """
        metadata_path = DOJO_ROOT / f"{voice_name}_dojo" / "dataset" / "metadata.csv"
        try:
            # Sort numerically by ID before saving
            def numeric_key(entry):
                id_val = entry.get('id', '')
                return int(id_val) if id_val.isdigit() else id_val
            
            entries.sort(key=numeric_key)

            with open(metadata_path, "w", encoding="utf-8", newline="\n") as f:
                for entry in entries:
                    f.write(f"{entry['id']}|{entry['text']}\n")
            
            # Invalidate caches since file was modified
            if voice_name in self._metadata_cache:
                del self._metadata_cache[voice_name]
            if voice_name in self._wav_stats_cache:
                del self._wav_stats_cache[voice_name]
            
            return True
        except Exception as e:
            logger.error(f"Error saving metadata: {e}")
            return False

    def ignore_wavs(self, voice_name: str, ids: List[str], delete_files: bool = False) -> Dict[str, Any]:
        """
        Removes specific wav IDs from the metadata and optionally deletes the physical files.
        """
        metadata = self.get_metadata(voice_name)
        ids_to_remove = set(ids)
        
        new_metadata = [e for e in metadata if e['id'] not in ids_to_remove]
        
        if len(new_metadata) == len(metadata) and not delete_files:
            return {"ok": True, "message": "No IDs found to remove."}
        
        success = self.save_metadata(voice_name, new_metadata)
        if not success:
            return {"ok": False, "error": "Failed to update metadata.csv"}
        
        removed_files = 0
        if delete_files:
            dataset_dir = DOJO_ROOT / f"{voice_name}_dojo" / "dataset"
            for wav_id in ids:
                wav_path = dataset_dir / f"{wav_id}.wav"
                if wav_path.exists():
                    try:
                        wav_path.unlink()
                        removed_files += 1
                    except Exception as e:
                        logger.error(f"Failed to delete {wav_path}: {e}")

        return {
            "ok": True, 
            "removed_from_metadata": len(metadata) - len(new_metadata),
            "files_deleted": removed_files
        }

    def generate_configs(self, voice_name: str, quality: str = "Medium", gender: str = "Female", language: str = "en-us"):
        """
        Generates the internal marker files (.QUALITY, .SCRATCH, .SAMPLING_RATE) and 
        dataset.conf required by the Piper training docker container.
        This effectively "primes" a dojo for its first training run.
        """
        dojo_name = f"{voice_name}_dojo"
        dojo_path = DOJO_ROOT / dojo_name
        dataset_path = dojo_path / "dataset"
        dataset_path.mkdir(parents=True, exist_ok=True)
            
        # Standardize quality codes (L/M/H)
        q_map = {"Low": "L", "Medium": "M", "High": "H", "L": "L", "M": "M", "H": "H"}
        q_code = q_map.get(quality, "M")
        
        target_dataset_path = dojo_path / "target_voice_dataset"
        target_dataset_path.mkdir(parents=True, exist_ok=True)
        scripts_path = dojo_path / "scripts"
        scripts_path.mkdir(parents=True, exist_ok=True)

        # Write core quality markers used by bash scripts
        for p in (dataset_path, target_dataset_path):
            with open(p / ".QUALITY", "w", encoding="utf-8", newline="\n") as f:
                f.write(f"{q_code}\n")
            with open(p / ".SCRATCH", "w", encoding="utf-8", newline="\n") as f:
                f.write("false\n")

        # Set sampling rate based on quality level.
        # NOTE: Piper's preprocessor only supports 16000 and 22050 Hz.
        # 44100 Hz is NOT a valid Piper training sample rate and will cause
        # preprocessing errors. High quality uses 22050 (the Piper maximum).
        sample_rate = "22050"
        if quality == "Low": sample_rate = "16000"
        # High stays at 22050 — 44100 is unsupported by piper_train.preprocess
        
        with open(scripts_path / ".SAMPLING_RATE", "w", encoding="utf-8", newline='\n') as f:
            f.write(f"{sample_rate}\n")

        # Worker Stability Safeguard: 
        # Piper's preprocessing logic can crash with division-by-zero errors if the 
        # file count is too low relative to the worker process count.
        num_wavs = len(list(dataset_path.glob("wav/*.wav")))
        workers = 4
        if num_wavs > 0 and num_wavs < 8:
            workers = 1 # Force single-threaded for tiny datasets to avoid division error
            logger.info(f"Tiny dataset detected for {voice_name} ({num_wavs} files). Using 1 worker for stability.")
        
        with open(scripts_path / ".MAX_WORKERS", "w", encoding="utf-8", newline='\n') as f:
            f.write(f"{workers}\n")

        # Generate dataset.conf - the primary config file for several bash scripts.
        g_code = gender[0].upper() if gender else "F"
        conf_content = f"""# Auto-generated by Piper Voice Studio
NAME="{voice_name}"
DESCRIPTION="Custom voice created via Web UI"
DEFAULT_VOICE_TYPE="{g_code}"
LOW_AUDIO="wav_16000"
MEDIUM_AUDIO="wav_22050"
HIGH_AUDIO="wav_44100"
ESPEAK_LANGUAGE_IDENTIFIER="{language}"
PIPER_FILENAME_PREFIX="en_US"
"""
        # Distribute the config to both the main dataset and the 'target' mirror
        for p in (dataset_path, target_dataset_path):
            with open(p / "dataset.conf", "w", encoding="utf-8", newline="\n") as f:
                f.write(conf_content)

        # Pre-load the best starting point (finetuning baseline).
        # We always check this to ensure the baseline matches the current settings.
        self.link_pretrained_checkpoint(voice_name, quality, gender)

    def link_pretrained_checkpoint(self, voice_name: str, quality: str, gender: str):
        """
        Copies the most relevant 'official' Piper pretrained model into the dojo.
        This provides a high-quality baseline so that custom training (finetuning) 
        takes minutes instead of weeks.
        """
        dojo_name = f"{voice_name}_dojo"
        dojo_path = DOJO_ROOT / dojo_name
        
        # Determine the source folder based on user-selected gender and quality.
        g_dir = "F_voice" if (gender and gender.upper().startswith("F")) else "M_voice"
        q_dir = (quality or "Medium").lower()
        if q_dir not in ["low", "medium", "high"]: 
            q_dir = "medium"
        
        # Pretrained models are stored in a central repository folder.
        # Try gender-specific folder first, then fall back to "shared" folder.
        checkpoint_src_dir = DOJO_ROOT / "PRETRAINED_CHECKPOINTS" / "default" / g_dir / q_dir
        if not checkpoint_src_dir.exists() or not list(checkpoint_src_dir.glob("*.ckpt")):
            checkpoint_src_dir = DOJO_ROOT / "PRETRAINED_CHECKPOINTS" / "default" / "shared" / q_dir
        dest_dir = dojo_path / "pretrained_tts_checkpoint"
        
        if not checkpoint_src_dir.exists():
            logger.warning(f"Pretrained source folder missing: {checkpoint_src_dir}")
            return
            
        ckpts = list(checkpoint_src_dir.glob("*.ckpt"))
        if not ckpts:
            logger.warning(f"No .ckpt files found in {checkpoint_src_dir}. Training will start from scratch.")
            return
            
        src_ckpt = ckpts[0]
        dest_dir.mkdir(parents=True, exist_ok=True)
        
        # Check if the desired checkpoint is already in place to avoid unnecessary IO
        dest_ckpt = dest_dir / src_ckpt.name
        if dest_ckpt.exists() and dest_ckpt.stat().st_size == src_ckpt.stat().st_size:
            logger.info(f"Pretrained checkpoint {src_ckpt.name} already linked.")
            return

        # Sweep existing manual checkpoints to ensure the new baseline is cleanly applied.
        for item in dest_dir.glob("*.ckpt"):
            try:
                if item.is_symlink() or item.is_file(): 
                    item.unlink()
            except: pass
            
        logger.info(f"Linking pretrained checkpoint for {voice_name}: {src_ckpt.name}...")
        
        try:
            # We copy instead of symlink to maintain portability within Docker containers.
            shutil.copy2(src_ckpt, dest_ckpt)
            logger.info(f"Successfully prepared pretrained checkpoint for {voice_name}")
        except Exception as e:
            logger.error(f"Failed to copy checkpoint for {voice_name}: {e}")

    def start_training(self, voice_name: str, start_mode: str | None = None) -> Dict[str, Any]:
        """
        Triggers the training lifecycle for a voice.
        1. Validates the dataset/metadata alignment.
        2. Clears stale preprocessed cache if necessary.
        3. Invokes the PowerShell 'run_training.ps1' script to launch Docker.
        """
        dojo_name = f"{voice_name}_dojo"
        script_dir = ROOT_DIR / "training" / "make piper voice models"
        script_path = script_dir / "run_training.ps1"

        dojo_path = DOJO_ROOT / dojo_name
        dataset_path = dojo_path / "dataset"
        wav_folder = dataset_path / "wav"
        metadata_path = dataset_path / "metadata.csv"
        training_folder = dojo_path / "training_folder"
        dataset_jsonl = training_folder / "dataset.jsonl"

        def _count_lines(path: Path) -> int:
            """Effeciently counts lines in a text file by streaming the generator."""
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    return sum(1 for _ in f)
            except Exception:
                return 0

        def _purge_preprocessed_training_folder() -> None:
            """
            Deletes cached preprocessing artifacts to ensure the next 
            training run starts with fresh data.
            """
            try:
                shutil.rmtree(training_folder / "cache", ignore_errors=True)
            except Exception:
                pass
            for p in (training_folder / "config.json", training_folder / "dataset.jsonl"):
                try:
                    if p.exists():
                        p.unlink()
                except Exception:
                    pass

        def _dataset_preflight() -> Dict[str, Any]:
            """
            Verification suite to ensure the data is in the correct format for Piper.
            Checks for existence of audio files and their corresponding metadata entries.
            Also validates and cleans metadata for Whisper hallucinations.
            """
            # First, validate and clean the metadata.csv file if it exists
            # This only runs when starting training, not after transcription
            if metadata_path.exists():
                try:
                    from auto_transcribe import validate_and_fix_metadata_csv
                    is_valid, num_fixes, validation_errors = validate_and_fix_metadata_csv(metadata_path)
                    if num_fixes > 0:
                        logger.info(f"Pre-training validation applied {num_fixes} fix(es) for {voice_name}")
                        # Only purge cache if significant fixes were made (5+ lines removed)
                        # This prevents cache churning for minor corrections
                        if num_fixes >= 5 and dataset_jsonl.exists():
                            logger.info(f"Purging preprocessing cache due to significant metadata fixes ({num_fixes} changes)")
                            _purge_preprocessed_training_folder()
                        elif num_fixes < 5 and dataset_jsonl.exists():
                            logger.info(f"Minor metadata fixes ({num_fixes} changes) - keeping existing preprocessing cache")
                except Exception as e:
                    logger.warning(f"Could not validate metadata for {voice_name}: {e}")
            
            wav_ids: List[str] = []
            if wav_folder.exists():
                # Extract all wav IDs currently in the dojo's dataset
                wav_ids = sorted([p.stem for p in wav_folder.glob("*.wav") if p.is_file()])

            # Error block: No audio means nothing to train on
            if not wav_ids:
                return {
                    "ok": False,
                    "code": "DATASET_EMPTY",
                    "error": "No WAV files found in dataset/wav for this voice.",
                    "fix": "Add audio clips to dataset/wav (or upload/slice master audio), then transcribe (or fill metadata) before training.",
                }

            # Check metadata file
            meta_entries = self.get_metadata(voice_name)
            meta_ids = {e.get("id", "").strip() for e in meta_entries if e.get("id")}
            meta_ids.discard("")

            # Error block: Audio exists but metadata.csv is missing or empty
            if (not metadata_path.exists()) or (len(meta_ids) == 0):
                return {
                    "ok": False,
                    "code": "METADATA_MISSING",
                    "error": "Missing metadata.csv (or it has no valid entries).",
                    "details": {"wav_count": len(wav_ids), "metadata_path": str(metadata_path)},
                    "fix": "Transcribe will generate metadata.csv automatically; you can also fill it manually if you prefer.",
                }

            # Comparison block: Every .wav file MUST have a matching line in metadata.csv
            missing_meta = [wid for wid in wav_ids if wid not in meta_ids]
            if missing_meta:
                return {
                    "ok": False,
                    "code": "METADATA_INCOMPLETE",
                    "error": "metadata.csv does not cover all WAV files in dataset/wav.",
                    "details": {
                        "wav_count": len(wav_ids),
                        "metadata_count": len(meta_ids),
                        "missing_count": len(missing_meta),
                        "missing_ids": missing_meta,
                        "missing_ids_sample": missing_meta[:25],
                    },
                    "fix": "Transcribe again so metadata.csv includes every wav (or manually add the missing rows).",
                }

            # Cache Invalidation: 
            # If the Piper preprocessor (dataset.jsonl) already exists but its line count 
            # doesn't match the current metadata record, the cache is "stale" and must be cleared.
            if dataset_jsonl.exists():
                jsonl_count = _count_lines(dataset_jsonl)
                if jsonl_count and jsonl_count != len(meta_ids):
                    logger.info(
                        f"Stale preprocessing detected for {voice_name}: dataset.jsonl has {jsonl_count} rows but metadata has {len(meta_ids)}. Purging cache to force re-preprocess."
                    )
                    _purge_preprocessed_training_folder()

            # --- Clip Duration Check ---
            # Clips that are too short (<0.5s) are acoustically useless and can
            # destabilize training. Clips that are too long (>15s) often contain
            # multiple sentences and produce poor alignments. Neither is caught
            # by any other validation step, so we check here using stdlib wave.
            import wave as _wave
            MIN_CLIP_SECONDS = 0.5
            MAX_CLIP_SECONDS = 15.0
            short_clips: List[str] = []
            long_clips: List[str] = []
            for wav_id in wav_ids:
                wav_path = wav_folder / f"{wav_id}.wav"
                try:
                    with _wave.open(str(wav_path), "r") as wf:
                        frames = wf.getnframes()
                        rate = wf.getframerate()
                        if rate > 0:
                            duration = frames / rate
                            if duration < MIN_CLIP_SECONDS:
                                short_clips.append(wav_id)
                            elif duration > MAX_CLIP_SECONDS:
                                long_clips.append(wav_id)
                except Exception:
                    pass  # Unreadable files are caught by the corrupted-audio cleaner
            if short_clips or long_clips:
                details: Dict[str, Any] = {}
                if short_clips:
                    details["short_clips_count"] = len(short_clips)
                    details["short_clips_sample"] = short_clips[:10]
                    details["short_threshold_seconds"] = MIN_CLIP_SECONDS
                if long_clips:
                    details["long_clips_count"] = len(long_clips)
                    details["long_clips_sample"] = long_clips[:10]
                    details["long_threshold_seconds"] = MAX_CLIP_SECONDS
                logger.warning(
                    f"Clip duration issues for {voice_name}: "
                    f"{len(short_clips)} short (<{MIN_CLIP_SECONDS}s), "
                    f"{len(long_clips)} long (>{MAX_CLIP_SECONDS}s)"
                )
                # Warn but do not block — the user may have intentionally kept these
                return {
                    "ok": True,
                    "wav_count": len(wav_ids),
                    "metadata_count": len(meta_ids),
                    "warnings": ["Some clips have unusual durations — see details for IDs."],
                    "duration_issues": details,
                }

            return {"ok": True, "wav_count": len(wav_ids), "metadata_count": len(meta_ids)}

        def _normalize_dataset_volume() -> None:
            """
            Normalises every WAV clip in the dataset to a consistent peak dBFS
            level. Inconsistent recording volumes are a common source of training
            instability and audible quality drops in the final model.

            Uses only stdlib (wave + array) so no extra dependencies are required.
            Target: -3 dBFS peak. Files already within 1 dB of target are skipped
            to avoid unnecessary writes.
            """
            import wave as _wave
            import array as _array
            import math as _math

            TARGET_PEAK_DBFS = -3.0  # headroom below digital full-scale
            TOLERANCE_DB = 1.0       # skip file if already within ±1 dB of target
            target_peak_linear = 10 ** (TARGET_PEAK_DBFS / 20.0)

            adjusted = 0
            skipped = 0
            errors = 0

            for wav_path in sorted(wav_folder.glob("*.wav")):
                try:
                    with _wave.open(str(wav_path), "r") as wf:
                        n_channels = wf.getnchannels()
                        sampwidth = wf.getsampwidth()
                        framerate = wf.getframerate()
                        n_frames = wf.getnframes()
                        raw = wf.readframes(n_frames)

                    if sampwidth != 2:  # Only handle 16-bit PCM
                        skipped += 1
                        continue

                    samples = _array.array("h", raw)  # signed 16-bit
                    if not samples:
                        skipped += 1
                        continue

                    peak = max(abs(s) for s in samples)
                    if peak == 0:
                        skipped += 1
                        continue

                    current_peak_dbfs = 20 * _math.log10(peak / 32768.0)
                    if abs(current_peak_dbfs - TARGET_PEAK_DBFS) <= TOLERANCE_DB:
                        skipped += 1
                        continue

                    gain = target_peak_linear / (peak / 32768.0)
                    # Clamp to avoid clipping
                    samples = _array.array(
                        "h",
                        [max(-32768, min(32767, int(s * gain))) for s in samples]
                    )

                    with _wave.open(str(wav_path), "w") as wf:
                        wf.setnchannels(n_channels)
                        wf.setsampwidth(sampwidth)
                        wf.setframerate(framerate)
                        wf.writeframes(samples.tobytes())

                    adjusted += 1
                except Exception as exc:
                    logger.debug(f"Volume normalisation skipped {wav_path.name}: {exc}")
                    errors += 1

            logger.info(
                f"Volume normalisation for {voice_name}: "
                f"{adjusted} adjusted, {skipped} already OK, {errors} errors"
            )

        def _launch_training_process() -> Dict[str, Any]:
            """
            Final step of initiation: executes the PowerShell script to start 
            containerized training.
            """
            # Ensure marker files and configuration are synced before starting
            try:
                current_settings = self.get_dojo_settings(voice_name)
                self.generate_configs(
                    voice_name, 
                    quality=current_settings.get("quality", "Medium"),
                    gender=current_settings.get("gender", "Female"),
                    language=current_settings.get("language", "en-us")
                )
            except Exception as e:
                logger.error(f"Config generation failed: {e}")

            # Define standard training log path
            log_file = DOJO_ROOT / dojo_name / "training_log.txt"
            log_file.parent.mkdir(parents=True, exist_ok=True)

            # Validate start mode: Scratch, Pretrained, or Resume (defaults to Resume if possible)
            mode = (start_mode or "").strip().lower()
            if mode and mode not in ("resume", "pretrained", "scratch"):
                return {"ok": False, "error": f"Invalid start_mode: {start_mode}. Use resume|pretrained|scratch."}

            # SAFETY CHECK: Validate checkpoint quality matches dojo quality setting
            # This prevents training failures due to architecture mismatches
            if mode != "scratch":  # Only check if resuming or using pretrained
                checkpoint_path = dojo_path / "voice_checkpoints"
                if checkpoint_path.exists():
                    # Find the latest checkpoint
                    ckpts = sorted(checkpoint_path.glob("epoch=*.ckpt"), key=lambda p: p.stat().st_mtime, reverse=True)
                    if ckpts:
                        latest_ckpt = ckpts[0]
                        try:
                            # Try to detect checkpoint quality by file size heuristic
                            # High quality checkpoints are typically larger (>800MB)
                            # Medium quality checkpoints are typically ~400-600MB
                            # Low quality checkpoints are typically <300MB
                            ckpt_size_mb = latest_ckpt.stat().st_size / (1024 * 1024)
                            
                            ckpt_quality = None
                            if ckpt_size_mb > 800:
                                ckpt_quality = "high"
                            elif ckpt_size_mb > 300:
                                ckpt_quality = "medium"
                            elif ckpt_size_mb > 0:
                                ckpt_quality = "low"
                            
                            if ckpt_quality:
                                current_quality = current_settings.get("quality", "Medium").lower()
                                
                                if ckpt_quality != current_quality:
                                    logger.warning(
                                        f"Quality mismatch detected for {voice_name}: "
                                        f"Checkpoint appears to be {ckpt_quality} ({ckpt_size_mb:.0f}MB) but dojo is configured for {current_quality}. "
                                        f"Auto-correcting dojo quality to match checkpoint."
                                    )
                                    
                                    # Auto-fix: Update quality markers to match checkpoint
                                    quality_code = {"high": "H", "medium": "M", "low": "L"}[ckpt_quality]
                                    for quality_file in [
                                        dojo_path / "dataset" / ".QUALITY",
                                        dojo_path / "target_voice_dataset" / ".QUALITY",
                                    ]:
                                        if quality_file.exists():
                                            quality_file.write_text(quality_code, encoding="utf-8")
                                    
                                    # Regenerate configs with correct quality
                                    self.generate_configs(
                                        voice_name,
                                        quality=ckpt_quality.capitalize(),
                                        gender=current_settings.get("gender", "Female"),
                                        language=current_settings.get("language", "en-us")
                                    )
                                    logger.info(f"Successfully corrected quality setting for {voice_name}")
                        except Exception as e:
                            logger.debug(f"Could not validate checkpoint quality: {e}")
                            # Non-critical error; allow training to proceed

            mode_arg = f" -StartMode '{mode}'" if mode else ""
            
            # Construct a complex PowerShell command string that logs output AND handles execution location
            ps_command = f"Set-Location -Path '{script_dir}'; ./run_training.ps1 -SelectedDojo '{dojo_name}' -Auto:$true{mode_arg} *>&1 | Tee-Object -FilePath '{log_file}'"

            cmd = [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                ps_command,
            ]

            try:
                logger.info(f"Launching training: {cmd}")
                # Reset safety state before start
                self.reset_thermal_trip(voice_name)
                self.reset_disk_trip(voice_name)

                # Reset early-stopping state for a fresh start or resume session
                if voice_name in self._early_stopping_stats:
                    del self._early_stopping_stats[voice_name]
                if voice_name in self._early_stopped_voices:
                    self._early_stopped_voices.remove(voice_name)
                
                # Remove stop marker if it exists (user is starting training again)
                stop_marker = dojo_path / ".STOPPED"
                if stop_marker.exists():
                    try:
                        stop_marker.unlink()
                        logger.info(f"Removed stop marker for {voice_name} - starting training")
                    except Exception as e:
                        logger.debug(f"Could not remove stop marker: {e}")

                # Execute as an asynchronous subprocess.
                # We do NOT block the server here; we track the process handle instead.
                proc = subprocess.Popen(
                    cmd,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                    stdin=subprocess.PIPE,
                    stdout=None,
                    stderr=None,
                    text=True,
                    bufsize=1,
                )
                self._training_processes[voice_name] = proc
                
                # Mark Docker image as installed in config (for offline detection)
                try:
                    # Avoid circular import by accessing the common utility directly
                    from common_utils import safe_config_load, safe_config_save
                    config_path = ROOT_DIR / "src" / "config.json"
                    if config_path.exists():
                        cfg = safe_config_load(config_path)
                        cfg["docker_installed"] = True
                        safe_config_save(config_path, cfg)
                except Exception as e:
                    logger.debug(f"Could not mark Docker as installed: {e}")
                
                # Clear preprocessing-only flag since this is actual training
                if voice_name in self._preprocessing_only_mode:
                    del self._preprocessing_only_mode[voice_name]
                    logger.info(f"Cleared preprocessing-only mode for {voice_name} - starting full training")
                return {"ok": True}
            except Exception as e:
                logger.error(f"Failed to launch training: {e}")
                return {"ok": False, "error": str(e)}

        # PREFLIGHT & AUTO-PIPELINE LOGIC
        # -------------------------------------------------------------------------
        # This section determines whether we can start training immediately, or 
        # if we need to run background transcription first to fix an invalid dataset.
        try:
            pre = _dataset_preflight()
            if not pre.get("ok"):
                # If the ONLY thing wrong is missing metadata, start an "Auto-Transcribe -> Train" pipeline.
                if pre.get("code") in ("METADATA_MISSING", "METADATA_INCOMPLETE"):
                    
                    # Safety check: Don't start a second transcription if one is already in progress.
                    if voice_name in self._transcription_stats:
                        self._auto_pipeline_state[voice_name] = {
                            "phase": "transcribing",
                            "message": "Transcription already running.",
                            "started_at": time.time(),
                        }
                        return {"ok": True, "phase": "transcribing", "message": "Transcribing dataset..."}

                    # Thread safety: ensure only one auto-pipeline runs per voice at a time.
                    existing = self._auto_pipeline_threads.get(voice_name)
                    if existing and existing.is_alive():
                        st = self._auto_pipeline_state.get(voice_name, {})
                        return {"ok": True, "phase": st.get("phase", "transcribing"), "message": st.get("message", "Working...")}

                    self._auto_pipeline_state[voice_name] = {
                        "phase": "transcribing",
                        "message": "Auto-transcribing dataset to fill metadata.csv...",
                        "started_at": time.time(),
                    }

                    def _pipeline_worker():
                        """Background worker to orchestrate transcription-before-training."""
                        try:
                            self._auto_pipeline_state[voice_name]["phase"] = "transcribing"
                            self._auto_pipeline_state[voice_name]["message"] = "Running Whisper transcription..."
                            
                            # Determine missing files (for partial updates) vs total transcription (for new dojos)
                            missing_ids = None
                            if pre.get("code") == "METADATA_INCOMPLETE":
                                missing_ids = (pre.get("details") or {}).get("missing_ids")

                            tr = self.run_transcription(voice_name, wav_ids=missing_ids, replace_existing=False)
                            if not tr.get("ok"):
                                self._auto_pipeline_state[voice_name] = {
                                    "phase": "failed",
                                    "message": "Transcription failed.",
                                    "error": tr.get("error", "Unknown transcription error"),
                                    "started_at": time.time(),
                                }
                                return

                            # Re-verify the dataset now that transcription is "finished"
                            pre2 = _dataset_preflight()
                            if not pre2.get("ok"):
                                error_handled = False

                                # AUTO-PRUNE: If files are still missing metadata after we explicitly tried to fix them,
                                # they are likely corrupt or unreadable audio files. Move them out of the way so training can start.
                                if pre2.get("code") == "METADATA_INCOMPLETE":
                                    still_missing = (pre2.get("details") or {}).get("missing_ids", [])
                                    if still_missing:
                                        msg = f"Removing {len(still_missing)} unfixable file(s) from dataset..."
                                        self._auto_pipeline_state[voice_name]["message"] = msg
                                        logger.info(f"{voice_name}: {msg}")

                                        ignore_dir = dataset_path / "ignore"
                                        ignore_dir.mkdir(exist_ok=True)

                                        for bad_id in still_missing:
                                            src_wav = wav_folder / f"{bad_id}.wav"
                                            if src_wav.exists():
                                                try:
                                                    tgt_wav = ignore_dir / f"{bad_id}.wav"
                                                    if tgt_wav.exists(): tgt_wav.unlink()
                                                    shutil.move(str(src_wav), str(tgt_wav))
                                                except Exception as ex:
                                                    logger.warning(f"Failed to move broken file {bad_id}: {ex}")

                                        # Third check - hopefully passing now
                                        pre3 = _dataset_preflight()
                                        if pre3.get("ok"):
                                            error_handled = True
                                        else:
                                            # Update error with new status
                                            pre2 = pre3

                                if not error_handled:
                                    self._auto_pipeline_state[voice_name] = {
                                        "phase": "failed",
                                        "message": "Dataset still invalid after cleanup attempts.",
                                        "error": pre2.get("error", "Unknown dataset error"),
                                        "details": pre2.get("details"),
                                        "started_at": time.time(),
                                    }
                                    return

                            # Everything looks good: wipe stale cache and finally start training.
                            _purge_preprocessed_training_folder()
                            self._auto_pipeline_state[voice_name]["phase"] = "normalizing_audio"
                            self._auto_pipeline_state[voice_name]["message"] = "Normalising clip volumes..."
                            _normalize_dataset_volume()
                            self._auto_pipeline_state[voice_name]["phase"] = "starting_training"
                            self._auto_pipeline_state[voice_name]["message"] = "Starting Piper training..."

                            launched = _launch_training_process()
                            if not launched.get("ok"):
                                self._auto_pipeline_state[voice_name] = {
                                    "phase": "failed",
                                    "message": "Failed to launch training.",
                                    "error": launched.get("error", "Unknown launch error"),
                                    "started_at": time.time(),
                                }
                            else:
                                # Successfully entered training phase
                                self._auto_pipeline_state[voice_name]["phase"] = "running"
                                self._auto_pipeline_state[voice_name]["message"] = "Training in progress."
                                return

                            self._auto_pipeline_state[voice_name] = {
                                "phase": "running",
                                "message": "Training running.",
                                "started_at": time.time(),
                            }
                        except Exception as e:
                            self._auto_pipeline_state[voice_name] = {
                                "phase": "failed",
                                "message": "Auto pipeline crashed.",
                                "error": str(e),
                                "started_at": time.time(),
                            }

                    t = threading.Thread(target=_pipeline_worker, daemon=True)
                    self._auto_pipeline_threads[voice_name] = t
                    t.start()
                    return {"ok": True, "phase": "transcribing", "message": "Auto-transcribing, then training will start automatically."}

                # Non-metadata failures should still block with a clear message
                return pre
        except Exception as e:
            # Preflight errors indicate serious data problems - don't start training
            logger.error(f"Dataset preflight check failed: {e}")
            return {"ok": False, "error": f"Preflight validation error: {str(e)}"}
        
        if not script_path.exists():
            return {"ok": False, "error": f"run_training.ps1 not found at {script_path}"}

        # If we get here, dataset is valid and we can launch training immediately.
        _normalize_dataset_volume()
        return _launch_training_process()

    def stop_training(self, voice_name: str, deep_cleanup: bool = False) -> Dict[str, Any]:
        """
        Signals the training environment to stop immediately.
        Calls 'stop_container.ps1' which handles docker cleanups and saves.
        If deep_cleanup is True, also performs WSL shutdown to reclaim memory.
        """
        script_dir = ROOT_DIR / "training" / "make piper voice models"
        script_path = script_dir / "stop_container.ps1"
        
        if not script_path.exists():
            # Fallback to direct CLI if the helper script is missing
            try:
                subprocess.run(["docker", "stop", "textymcspeechy-piper"], capture_output=True, text=True, creationflags=0x08000000 if os.name == 'nt' else 0)
                return {"ok": True}
            except Exception as e:
                return {"ok": False, "error": str(e)}

        cmd = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-File", str(script_path)
        ]
        
        try:
            logger.info(f"Stopping training: {cmd}")
            result = subprocess.run(cmd, capture_output=True, text=True, creationflags=0x08000000 if os.name == 'nt' else 0)
            
            # Clean up all tracking state for this voice when explicitly stopped
            self._cleanup_training_state(voice_name, keep_preprocessing_flag=False)
            
            # Touch a marker file to signal explicit stop (prevents log_active_recently from triggering)
            dojo_name = f"{voice_name}_dojo"
            dojo_path = DOJO_ROOT / dojo_name
            stop_marker = dojo_path / ".STOPPED"
            try:
                stop_marker.touch()
            except Exception as e:
                logger.warning(f"Failed to create stop marker for {voice_name}: {e}")
                
            if result.returncode == 0:
                result_payload = {"ok": True}
                
                # Optional deep cleanup: shutdown WSL to reclaim all GPU memory
                if deep_cleanup:
                    try:
                        logger.info("Performing deep cleanup: shutting down WSL...")
                        cleanup_result = subprocess.run(
                            ["wsl", "--shutdown"],
                            capture_output=True,
                            text=True,
                            creationflags=0x08000000 if os.name == 'nt' else 0,
                            timeout=30
                        )
                        if cleanup_result.returncode == 0:
                            result_payload["deep_cleanup"] = "WSL shutdown successful"
                        else:
                            result_payload["deep_cleanup_warning"] = f"WSL shutdown failed: {cleanup_result.stderr}"
                    except Exception as cleanup_err:
                        logger.warning(f"Deep cleanup failed: {cleanup_err}")
                        result_payload["deep_cleanup_warning"] = str(cleanup_err)
                
                return result_payload
            else:
                return {"ok": False, "error": result.stderr}
        except Exception as e:
            logger.error(f"Failed to stop training: {e}")
            return {"ok": False, "error": str(e)}

    def ensure_tensorboard(self, voice_name: str):
        """
        Verification helper to ensure TensorBoard is active inside the Docker container.
        This provides real-time loss graphs in the web UI.
        """
        try:
            # First, check if the training container itself is still alive
            check_cmd = ["docker", "ps", "-f", "name=textymcspeechy-piper", "--format", "{{.Names}}"]
            result = subprocess.run(check_cmd, capture_output=True, text=True, creationflags=0x08000000 if os.name == 'nt' else 0)
            if "textymcspeechy-piper" not in result.stdout:
                return

            # Check if a tensorboard process is already running in the background of that container
            ps_cmd = ["docker", "exec", "textymcspeechy-piper", "ps", "aux"]
            ps_result = subprocess.run(ps_cmd, capture_output=True, text=True, creationflags=0x08000000 if os.name == 'nt' else 0)
            if "tensorboard" in ps_result.stdout:
                return

            # Determine the internal log directory based on the voice being trained
            dojo_name = f"{voice_name}_dojo"
            log_dir = f"/app/tts_dojo/{dojo_name}/training_folder/lightning_logs"
            
            # Launch a detached TensorBoard instance listening on the standard port 6006
            launch_cmd = [
                "docker", "exec", "-d", "textymcspeechy-piper", 
                "tensorboard", "--logdir", log_dir, "--bind_all", "--port", "6006"
            ]
            subprocess.run(launch_cmd, creationflags=0x08000000 if os.name == 'nt' else 0)
            logger.info(f"Auto-launched TensorBoard for {voice_name}")
        except Exception as e:
            logger.error(f"Failed to auto-launch TensorBoard: {e}")

    def manual_checkpoint_save(self, voice_name: str) -> Dict[str, Any]:
        """
        Forcefully triggers the auto-save logic for the most recent checkpoint.
        Useful if a user wants to snapshot progress immediately.
        """
        dojo_path = DOJO_ROOT / f"{voice_name}_dojo"
        ckpt_dir = dojo_path / "training_folder" / "lightning_logs" / "version_0" / "checkpoints"
        
        if not ckpt_dir.exists():
            return {"ok": False, "error": "No checkpoints found. Training may not have started yet."}

        try:
            ckpts = list(ckpt_dir.glob("*.ckpt"))
            if not ckpts:
                return {"ok": False, "error": "No .ckpt files found."}

            # Find the newest checkpoint by modification time
            newest = max(ckpts, key=lambda p: p.stat().st_mtime)
            
            # Execute the persistence logic synchronously
            self.perform_checkpoint_save(voice_name, newest)
            
            return {"ok": True, "checkpoint": newest.name}
        except Exception as e:
            logger.error(f"Manual checkpoint save failed: {e}")
            return {"ok": False, "error": str(e)}

    def send_training_input(self, voice_name: str, text: str) -> Dict[str, Any]:
        """
        Wires text input directly to the standard input of the active training process.
        Used to respond to prompts from the training scripts (e.g. confirming overrides).
        """
        proc = self._training_processes.get(voice_name)
        if not proc:
            return {"ok": False, "error": "No training session active for this voice."}
        
        if proc.poll() is not None:
            del self._training_processes[voice_name]
            return {"ok": False, "error": "Process has already terminated."}

        try:
            # Send the text + newline to simulate hitting Enter
            proc.stdin.write(text + "\n")
            proc.stdin.flush()
            logger.info(f"Sent input to training session ({voice_name}): {text}")
            return {"ok": True}
        except Exception as e:
            logger.error(f"Error sending input to training: {e}")
            # Clean up dead process
            self._cleanup_training_state(voice_name, keep_preprocessing_flag=False)
            return {"ok": False, "error": str(e)}

    def get_training_status(self, voice_name: str) -> Dict[str, Any]:
        """
        Aggregates real-time information about a voice's training session.
        Calculates disk usage, checks for latest models, and identifies if training is active.
        """
        dojo_name = f"{voice_name}_dojo"
        dojo_path = DOJO_ROOT / dojo_name
        checkpoints_dir = dojo_path / "training_folder" / "lightning_logs" / "version_0" / "checkpoints"
        voices_dir = dojo_path / "tts_voices"
        
        # Load the latest settings to ensure UI parity (quality, gender, etc)
        dojo_settings = self.get_dojo_settings(voice_name)
        
        status = {
            "is_running": False,
            "container_running": False,
            "voice_process_active": False,
            "log_active_recently": False,
            "latest_checkpoint": None,
            "last_epoch": None,
            "last_step": None,
            "logs": [],
            "available_models": [],
            "best_checkpoint": None,
            "last_error": None,
            "quality": dojo_settings.get("quality", "Medium"),
            "gender": dojo_settings.get("gender", "Female"),
            "language": dojo_settings.get("language", "en-us"),
            "free_space_gb": 0,
            "session_stats": {
                "ckpts_seen": 0,
                "avg_epoch_time": 0,
                "start_epoch": None
            },
            "metrics": {
                "loss_disc": None,
                "loss_gen": None,
                "loss_mel": None,
                "loss_kl": None
            },
            "thermal_tripped": voice_name in self._thermal_tripped_voices,
            "disk_tripped": voice_name in self._disk_tripped_voices,
            "transcribe_active": bool(self._transcription_stats.get(voice_name)),
            "transcribe_progress": self._transcription_stats.get(voice_name),
            "auto_pipeline": self._auto_pipeline_state.get(voice_name),
            "dojo_settings": self.get_dojo_settings(voice_name)
        }

        # Check session stats
        if voice_name in self._session_stats:
            stats = self._session_stats[voice_name]
            status["session_stats"]["ckpts_seen"] = stats["ckpts_seen"]
            status["session_stats"]["avg_epoch_time"] = stats["avg_epoch_time"]
            status["session_stats"]["start_epoch"] = stats.get("start_epoch")

        # Check disk space
        try:
            total, used, free = shutil.disk_usage(ROOT_DIR)
            status["free_space_gb"] = free // (2**30)
        except:
            pass

        # 0. Contextual metadata extraction
        # We've already loaded the base settings from self.get_dojo_settings(voice_name) above.
        # These secondary checks verify the current state of the filesystem.
        try:
            # Re-verify the absolute source of truth from the configuration files
            status["gender"] = dojo_settings.get("gender", "Female")
            status["language"] = dojo_settings.get("language", "en-us")
            status["quality"] = dojo_settings.get("quality", "Medium")
        except Exception as e:
            logger.warning(f"Failed to sync dojo settings for status: {e}")

        def _extract_error_from_logs(lines: list[str]) -> Dict[str, str] | None:
            """
            Heuristic-based error parser for Docker logs.
            Attempts to identify common failure modes (missing checkpoints, bad data)
            and provides a user-friendly 'fix' suggestion.
            """
            text = "\n".join(lines)

            # Case: Resuming from a checkpoint that was deleted or renamed
            m = re.search(r"Checkpoint at (.+?) not found", text)
            if m:
                path = m.group(1).strip()
                return {
                    "code": "CHECKPOINT_NOT_FOUND",
                    "title": "Checkpoint file not found",
                    "message": f"Training tried to resume from a checkpoint that doesn't exist: {path}",
                    "fix": "Enable 'Start Training from Scratch' or ensure the .ckpt exists in voice_checkpoints/.",
                }

            # Case: Transcription was skipped or failed silently
            if "dataset.jsonl" in text and ("DATASET MISSING" in text or "dataset.jsonl missing" in text or "FileNotFoundError" in text):
                return {
                    "code": "DATASET_JSONL_MISSING",
                    "title": "Dataset not preprocessed",
                    "message": "The training folder is missing training_folder/dataset.jsonl.",
                    "fix": "Run the Transcribe/Preprocess step again, then retry training.",
                }

            # Case: Phonemization failures (usually bad characters in metadata.csv)
            if "piper_train.preprocess failed" in text:
                return {
                    "code": "PREPROCESS_FAILED",
                    "title": "Preprocessing failed",
                    "message": "piper_train.preprocess exited with an error.",
                    "fix": "Scroll up in Docker Output for the first error line (often a missing dataset.conf, bad audio, or language mismatch).",
                }

            # Case: Out-of-memory or other Python crashes
            if "PIPER TRAINING FAILURE DETECTED" in text or "Traceback" in text:
                return {
                    "code": "TRAINING_FAILED",
                    "title": "Training failed",
                    "message": "Training exited with an error. See Docker Output for details.",
                    "fix": "Copy the Docker Output and look for the first Traceback/ERROR line.",
                }

            # Case: Docker daemon not running or connection failure
            if "failed to connect to the docker API" in text.lower() or "check if the daemon is running" in text.lower():
                return {
                    "code": "DOCKER_NOT_RUNNING",
                    "title": "Docker not running",
                    "message": "The Docker daemon is not responding. Training or export cannot proceed.",
                    "fix": "Ensure Docker Desktop is open and the engine has started (check your system tray for the whale icon).",
                }

            return None
        
        # 1. Check if the Docker container or local training process is currently active
        try:
            # Check for explicit stop marker first - if present, always return not running
            stop_marker = dojo_path / ".STOPPED"
            if stop_marker.exists():
                # Check if this stop is stale (older than 5 minutes)
                try:
                    age_s = time.time() - stop_marker.stat().st_mtime
                    if age_s < 300:  # 5 minutes
                        status["is_running"] = False
                        # Clean up any lingering process tracking
                        if voice_name in self._training_processes:
                            del self._training_processes[voice_name]
                        if voice_name in self._preprocessing_only_mode:
                            del self._preprocessing_only_mode[voice_name]
                            logger.info(f"Cleaned up preprocessing-only flag for stopped voice {voice_name}")
                        # Skip all other checks and return early
                        logger.debug(f"Stop marker detected for {voice_name}, forcing is_running=False")
                        # Continue with checkpoint/model detection but force not running
                    else:
                        # Old marker, remove it and proceed with normal checks
                        stop_marker.unlink()
                        logger.debug(f"Removed stale stop marker for {voice_name}")
                except Exception as e:
                    logger.debug(f"Error checking stop marker age: {e}")
            
            # Voice-specific process check (PowerShell wrapper that launches Docker and tees logs)
            if voice_name in self._training_processes:
                proc = self._training_processes[voice_name]
                if proc.poll() is None:
                    status["voice_process_active"] = True
                else:
                    # Cleanup finished local process tracking
                    del self._training_processes[voice_name]

            # Global container check (informational only; container may be up even when idle)
            res = subprocess.run(
                ["docker", "ps", "--filter", "name=textymcspeechy-piper", "--format", "{{.Names}}"],
                capture_output=True,
                text=True,
                creationflags=0x08000000 if os.name == 'nt' else 0,
            )
            status["container_running"] = "textymcspeechy-piper" in (res.stdout or "")

            # Log activity is a practical voice-specific signal even if the container stays running.
            # If the log has been written to recently, something is likely active for this voice.
            log_file = DOJO_ROOT / dojo_name / "training_log.txt"
            if log_file.exists():
                try:
                    age_s = time.time() - log_file.stat().st_mtime
                    status["log_active_recently"] = age_s < 120
                except Exception as e:
                    logger.debug(f"Error checking log file age for {voice_name}: {e}")

            # Voice-specific running determination
            # Smart detection: If preprocessing is complete (all samples processed), mark as done
            # even if the wrapper process or container is still running (common with PowerShell + Docker)
            preprocessing_complete = False
            preprocessing_detection_method = None  # Track which signal was used
            try:
                dataset_stats = self.get_dataset_stats(voice_name)
                
                # Check if counts match (primary signal)
                counts_match = (dataset_stats.get("preprocessed_count") > 0 and
                               dataset_stats.get("preprocessed_count") == dataset_stats.get("meta_count"))
                
                # Additional check: look for completion marker in log
                log_shows_complete = False
                log_shows_training = False
                log_file = DOJO_ROOT / dojo_name / "training_log.txt"
                if log_file.exists():
                    try:
                        # Check last 4KB of log for markers
                        with open(log_file, 'rb') as f:
                            f.seek(-min(4096, log_file.stat().st_size), 2)
                            tail = f.read().decode('utf-8', errors='ignore')
                            if "Preprocess Only mode complete" in tail or "Successfully preprocessed dataset" in tail:
                                log_shows_complete = True
                                preprocessing_detection_method = "log_marker"
                            if "Starting training loop" in tail or "Resuming from highest saved checkpoint" in tail:
                                log_shows_training = True
                    except Exception as e:
                        logger.debug(f"Error reading log tail for {voice_name}: {e}")
                
                # Mark complete if either signal is positive
                if counts_match:
                    preprocessing_complete = True
                    preprocessing_detection_method = "count_match"
                    logger.debug(f"Preprocessing complete for {voice_name}: {dataset_stats.get('preprocessed_count')}/{dataset_stats.get('meta_count')}")
                elif log_shows_complete:
                    preprocessing_complete = True
                    logger.debug(f"Preprocessing complete for {voice_name}: log confirmation found")
            except Exception as e:
                logger.warning(f"Error checking preprocessing completion for {voice_name}: {e}")
            
            if preprocessing_complete:
                is_preprocess_only = self._preprocessing_only_mode.get(voice_name, False)
                if is_preprocess_only:
                    # Preprocessing-only mode complete - clean up and mark as not running
                    logger.info(f"Preprocessing-only complete for {voice_name} (detected via {preprocessing_detection_method})")
                    self._cleanup_training_state(voice_name, keep_preprocessing_flag=True)
                    status["is_running"] = False
                else:
                    # Either training (don't terminate) or process already cleaned up
                    # But respect explicit stop marker
                    if stop_marker.exists():
                        try:
                            age_s = time.time() - stop_marker.stat().st_mtime
                            if age_s < 300:  # 5 minutes
                                status["is_running"] = False
                            else:
                                status["is_running"] = bool(status["voice_process_active"] or status["log_active_recently"])
                        except Exception as e:
                            logger.debug(f"Error checking stop marker age in training branch: {e}")
                            status["is_running"] = bool(status["voice_process_active"] or status["log_active_recently"])
                    else:
                        # If preprocessing is complete, only show as running if we see training activity
                        # or the wrapper process is explicitly active.
                        if not log_shows_training and not status["voice_process_active"]:
                            status["is_running"] = False
                        else:
                            status["is_running"] = bool(status["voice_process_active"] or status["log_active_recently"])
            else:
                # Respect explicit stop marker
                if stop_marker.exists():
                    try:
                        age_s = time.time() - stop_marker.stat().st_mtime
                        if age_s < 300:  # 5 minutes
                            status["is_running"] = False
                        else:
                            status["is_running"] = bool(status["voice_process_active"] or status["log_active_recently"])
                    except Exception as e:
                        logger.debug(f"Error checking stop marker in preprocessing branch: {e}")
                        status["is_running"] = bool(status["voice_process_active"] or status["log_active_recently"])
                else:
                    status["is_running"] = bool(status["voice_process_active"] or status["log_active_recently"])
        except Exception as e:
            logger.warning(f"Error checking training status for {voice_name}: {e}")

        # 2. Extract specific epoch/step progress from the newest checkpoint filename
        if checkpoints_dir.exists():
            ckpts = list(checkpoints_dir.glob("*.ckpt"))
            if ckpts:
                newest = max(ckpts, key=lambda p: p.stat().st_mtime)
                status["latest_checkpoint"] = newest.name
                match = re.search(r"epoch=(\d+)-step=(\d+)", newest.name)
                if match:
                    status["last_epoch"] = int(match.group(1))
                    status["last_step"] = int(match.group(2))

        # 3. List all ready-to-use ONNX models produced by this Dojo
        if voices_dir.exists():
            for p in voices_dir.glob("**/*.onnx"):
                if not p.name.startswith('.'):
                    # Ensure the JSON config also exists before listing it
                    # Piper requires both .onnx and .onnx.json (or .json) to verify the model is ready
                    json_candidates = [
                        p.with_suffix(".onnx.json"),
                        p.with_suffix(".json")
                    ]
                    if any(c.exists() for c in json_candidates):
                        # Try to read mel_loss from a companion metadata file
                        mel_loss_val = None
                        metadata_file = p.with_suffix(".onnx.mel_loss")
                        if metadata_file.exists():
                            try:
                                mel_loss_val = float(metadata_file.read_text().strip())
                            except:
                                pass
                        
                        status["available_models"].append({
                            "name": p.name,
                            "path": p.as_posix(),
                            "mtime": p.stat().st_mtime,
                            "mel_loss": mel_loss_val
                        })
            # Always show the newest models first in the UI dropdowns
            status["available_models"].sort(key=lambda x: x["mtime"], reverse=True)
            
            # Find the checkpoint with the lowest mel loss
            models_with_loss = [m for m in status["available_models"] if m.get("mel_loss") is not None]
            if models_with_loss:
                best = min(models_with_loss, key=lambda x: x["mel_loss"])
                status["best_checkpoint"] = {
                    "name": best["name"],
                    "mel_loss": best["mel_loss"]
                }

        # 4. Attempt to fetch live loss metrics via TensorBoard's tag system
        if status["is_running"]:
            try:
                # Map logical metrics to various tag naming conventions used by internal scripts
                tag_map = {
                    "loss_disc": ["loss_disc_all", "loss/disc/all"],
                    "loss_gen": ["loss_gen_all", "loss/gen/all"],
                    "loss_mel": ["loss_mel", "loss/mel", "loss_gen_all"], # Fallback choice
                    "loss_kl": ["loss_kl", "loss/kl"]
                }
                
                # We use a short timeout and try a few common tags
                for key, candidates in tag_map.items():
                    for tag in candidates:
                        # run=version_0 is the default for lightning
                        url = f"http://localhost:6006/data/plugin/scalars/scalars?tag={tag}&run=version_0"
                        try:
                            # Use short timeout to avoid blocking the main status poll
                            r = requests.get(url, timeout=0.2)
                            if r.status_code == 200:
                                data = r.json()
                                if data and len(data) > 0:
                                    # TensorBoard returns [wall_time, step, value]
                                    # We want the newest value (last in list)
                                    latest = data[-1]
                                    status["metrics"][key] = round(float(latest[2]), 4)
                                    break # Found a working tag for this key, move to next metric
                        except:
                            continue
                
                # Check for Early Stopping based on metrics
                self._check_early_stopping(voice_name, status["metrics"])
            except:
                pass

        # 5. Read logs efficiently by only tailing the end of the file
        log_file = dojo_path / "training_log.txt"
        if log_file.exists():
            try:
                def _try_fix_mojibake(s: str) -> str:
                    """Best-effort repair for UTF-8 bytes mis-decoded as cp1252/latin-1.

                    Common symptom in the Web UI: box drawing (e.g. "━") shows up as "â ...".
                    """
                    if not s:
                        return s
                    # Fast path: only attempt if it looks like mojibake.
                    if "â" not in s and "Γ" not in s:
                        return s
                    try:
                        return s.encode("latin-1", errors="strict").decode("utf-8", errors="strict")
                    except Exception:
                        return s

                # Optimized: Don't read whole file; only read last ~64KB
                max_read = 64 * 1024 
                file_size = log_file.stat().st_size
                
                with open(log_file, "rb") as f:
                    if file_size > max_read:
                        f.seek(-max_read, 2)
                    raw_data = f.read()
                
                # Try UTF-16 first, then fallback to UTF-8
                try:
                    content = raw_data.decode("utf-16")
                except UnicodeError:
                    content = raw_data.decode("utf-8", errors="ignore")
                
                # Filter out noisy debug logs and strip ANSI colors for clean display
                filtered_logs = []
                ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

                for line in content.splitlines():
                    cleaned = line.strip()
                    if not cleaned:
                        continue

                    cleaned = _try_fix_mojibake(cleaned)

                    # Filter specific noisy lines
                    if "DEBUG:fsspec.local:open file:" in cleaned:
                        continue
                    
                    # Filter mangled box drawing characters often seen in Windows logs
                    if "Γöö" in cleaned or "ΓöÇ" in cleaned:
                        continue

                    # Filter PowerShell wrapper noise that can be emitted when docker writes to stderr.
                    if cleaned.startswith("At ") and "run_training.ps1" in cleaned:
                        continue
                    if cleaned.startswith("+ ") and "docker exec" in cleaned:
                        continue
                    if cleaned.startswith("+ ~"):
                        continue
                    if cleaned.startswith("CategoryInfo") or cleaned.startswith("FullyQualifiedErrorId"):
                        continue
                    
                    # Remove ANSI codes for readability
                    cleaned = ansi_escape.sub('', cleaned)
                    
                    filtered_logs.append(cleaned)

                status["logs"] = filtered_logs[-100:]
                status["last_error"] = _extract_error_from_logs(status["logs"])
            except Exception as e:
                logger.error(f"Error reading log file: {e}")

        if status["is_running"]:
            status["thermal_tripped"] = False # Reset if running
        elif voice_name in self._thermal_tripped_voices:
            status["thermal_tripped"] = True
            
        if voice_name in self._early_stopped_voices and not status["is_running"]:
            status["early_stopped"] = True
                
        return status

    def get_active_training(self) -> Dict[str, Any]:
        """
        Fast scan for active training sessions across all dojos.
        Used by the Web UI for the 'Initializing Trainer...' badge and global status.
        """
        active_voices = []
        
        # 1. Check local tracked processes (from self.start_training)
        for v_name, proc in list(self._training_processes.items()):
            if proc.poll() is None:
                if v_name not in active_voices:
                    active_voices.append(v_name)
            else:
                # Cleanup finished local process tracking
                self._cleanup_training_state(v_name, keep_preprocessing_flag=True)

        # 2. Fallback: Check Docker directly for processes (covers server restarts)
        try:
            # Query docker for the list of processes inside the training container
            res = subprocess.run(
                ["docker", "exec", "textymcspeechy-piper", "ps", "aux"],
                capture_output=True,
                text=True,
                creationflags=0x08000000 if os.name == "nt" else 0,
            )
            
            if res.returncode == 0:
                # Heuristic: look for paths like /app/tts_dojo/VOICE_NAME_dojo/
                matches = re.findall(r"/app/tts_dojo/([^/\s]+)_dojo", res.stdout)
                for v in matches:
                    if v not in active_voices:
                        active_voices.append(v)
        except Exception:
            # Ignore docker errors here; it's a fallback mechanism
            pass
            
        return {
            "active": len(active_voices) > 0,
            "voices": sorted(list(set(active_voices))),
            "count": len(active_voices)
        }

    def trigger_export(self, voice_name: str, ckpt_filename: str) -> Dict[str, Any]:
        """
        Invokes the Linux-based ONNX export script inside the Docker container.
        This takes a PyTorch .ckpt and produces a runnable .onnx and .onnx.json file.
        """
        dojo_name = f"{voice_name}_dojo"
        dojo_path = DOJO_ROOT / dojo_name
        
        # Get prefix and quality from dataset.conf if possible
        prefix = "en_US"
        quality = "medium"
        try:
            conf_path = dojo_path / "dataset" / "dataset.conf"
            if conf_path.exists():
                txt = conf_path.read_text()
                m = re.search(r'PIPER_FILENAME_PREFIX="([^"]+)"', txt)
                if m: prefix = m.group(1)
            
            q_file = dojo_path / "dataset" / ".QUALITY"
            if q_file.exists():
                q_code = q_file.read_text().strip()
                quality = {"L": "low", "M": "medium", "H": "high"}.get(q_code, "medium")
        except: pass

        # Determine Epoch for identification
        epoch_match = re.search(r"epoch=(\d+)", ckpt_filename)
        epoch = epoch_match.group(1) if epoch_match else "ckpt"
        
        # Check if this is a "best" checkpoint logic
        is_best_ckpt = "best-" in ckpt_filename or "best_" in ckpt_filename
        
        # Use a distinct folder name for best checkpoints to protect them from "history cleanup"
        if is_best_ckpt:
            voice_folder = f"{voice_name}_best_{epoch}"
            onnx_filename = f"{prefix}-{voice_name}_{epoch}-best-{quality}.onnx"
        else:
            voice_folder = f"{voice_name}_{epoch}"
            onnx_filename = f"{prefix}-{voice_name}_{epoch}-{quality}.onnx"
        
        # These paths use '../' because the script inside docker is run from the 'scripts/' subfolder
        rel_ckpt = f"../voice_checkpoints/{ckpt_filename}"
        rel_onnx = f"../tts_voices/{voice_folder}/{onnx_filename}"
        
        logger.info(f"Exporting model to {onnx_filename} via Docker for {voice_name}...")
        
        # Command to run inside the container
        CONTAINER_NAME = "textymcspeechy-piper"
        cmd = [
            "docker", "exec", CONTAINER_NAME, "bash", "-c",
            f"cd /app/tts_dojo/{dojo_name}/scripts && bash utils/_tmux_piper_export.sh {rel_ckpt} {rel_onnx} {dojo_name}"
        ]
        
        try:
            # We use subprocess.run here
            result = subprocess.run(cmd, capture_output=True, text=True, creationflags=0x08000000 if os.name == 'nt' else 0)
            if result.returncode == 0:
                logger.info(f"SUCCESS: Created piper voice model {onnx_filename} for {voice_name}")
                
                # Determine Mel Loss for this file
                mel_loss_value = None
                
                # 1. Try to parse from filename (Source of Truth for "Best" checkpoints)
                # Format: best-epoch=123-loss=21.4567.ckpt
                loss_match = re.search(r"loss=([\d\.]+)", ckpt_filename)
                if loss_match:
                    try:
                        # Value in filename is SCALED -> Divide by 45 to get real loss
                        mel_loss_value = float(loss_match.group(1)) / 45.0
                    except: pass
                
                # 2. Fallback to live TensorBoard metrics if not in filename (for regular checkpoints)
                if mel_loss_value is None:
                    status = self.get_training_status(voice_name)
                    if status and status.get("metrics", {}).get("loss_mel") is not None:
                        mel_loss_value = status["metrics"]["loss_mel"] / 45.0
                
                # Save metadata
                if mel_loss_value is not None:
                    try:
                        voices_dir = dojo_path / "tts_voices"
                        for onnx_path in voices_dir.glob(f"**/{onnx_filename}"):
                            mel_loss_file = onnx_path.with_suffix(".onnx.mel_loss")
                            mel_loss_file.write_text(f"{mel_loss_value:.6f}")
                            logger.info(f"Saved mel loss {mel_loss_value:.6f} for {onnx_filename}")
                            break
                    except Exception as e:
                        logger.warning(f"Failed to save mel loss metadata: {e}")
                
                return {"ok": True, "filename": onnx_filename}
            else:
                logger.error(f"EXPORT FAILED for {voice_name}: {result.stderr}")
                return {"ok": False, "error": result.stderr}
        except Exception as e:
            logger.error(f"Export execution error for {voice_name}: {e}")
            return {"ok": False, "error": str(e)}

    def _check_thermal_safety(self):
        """
        Safety monitor that queries NVIDIA GPU temperatures.
        If the hardware exceeds the user-defined (or global default) threshold,
        training is immediately killed to prevent hardware damage.
        """
        if not self._training_processes:
            return

        try:
            # Prepare process flags for a silent execution on Windows
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE

            # Query nvidia-smi for the primary GPU's temperature
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, check=False,
                startupinfo=startupinfo
            )
            
            if result.returncode == 0:
                temp_str = result.stdout.strip().split('\n')[0]
                if temp_str.isdigit():
                    current_temp = int(temp_str)
                    
                    active_voices = list(self._training_processes.keys())
                    
                    # Iterate through all active sessions and check their specific limits
                    for voice in active_voices:
                        settings = self.get_dojo_settings(voice)
                        limit = settings.get("GPU_THERMAL_LIMIT_CELSIUS", self._gpu_thermal_limit)
                        
                        if current_temp >= limit:
                            logger.critical(f"THERMAL EMERGENCY: GPU reached {current_temp}C for '{voice}' (Limit: {limit}C). Stopping training!")
                            self.stop_training(voice)
                            self._thermal_tripped_voices.add(voice)
        except Exception as e:
            # Silently fail if nvidia-smi isn't available (e.g. CPU-only or non-NVIDIA system)
            logger.debug(f"Thermal safety check failed: {e}")

    def _check_disk_safety(self):
        """
        Disk space monitor to prevent full-disk system crashes.
        Piper checkpoints are large (100MB+), so running out of space is a common failure.
        """
        if not self._training_processes:
            return

        try:
            # Check the workspace root drive
            total, used, free = shutil.disk_usage(ROOT_DIR)
            free_gb = free // (2**30)
            
            active_voices = list(self._training_processes.keys())
            for voice in active_voices:
                settings = self.get_dojo_settings(voice)
                min_free = int(settings.get("MIN_FREE_SPACE_GB", 2))
                
                if free_gb < min_free:
                    logger.critical(f"DISK SPACE EMERGENCY: Free space {free_gb}GB is below limit {min_free}GB. Stopping training for '{voice}'!")
                    self.stop_training(voice)
                    self._disk_tripped_voices.add(voice)
        except Exception as e:
            logger.error(f"Disk safety check failed: {e}")

    def reset_thermal_trip(self, voice_name: str):
        """
        Clears the 'Thermal Tripped' status for a specific voice.
        Required before the user can attempt to restart training after a cooling period.
        """
        if voice_name in self._thermal_tripped_voices:
            self._thermal_tripped_voices.remove(voice_name)
            logger.info(f"Thermal protection reset for {voice_name}")
            return {"ok": True}
        return {"ok": False, "error": "Thermal trip not found"}

    def reset_disk_trip(self, voice_name: str):
        """
        Clears the 'Disk Tripped' and 'Early Stopped' status flags.
        Resets the session state so a voice can be resumed or retrained.
        """
        if voice_name in self._disk_tripped_voices:
            self._disk_tripped_voices.remove(voice_name)
        if voice_name in self._early_stopped_voices:
            self._early_stopped_voices.remove(voice_name)
        
        logger.info(f"Protection trips reset for {voice_name}")
        return {"ok": True}

    def _check_early_stopping(self, voice_name: str, metrics: Dict[str, float]):
        """
        Intelligent monitoring of Mel-Loss convergence.
        Stops training if the loss fails to improve significantly over a long period.
        Prevents wasting GPU power on models that are already 'cooked'.
        """
        if not metrics or "loss_mel" not in metrics:
            return

        current_loss = metrics["loss_mel"]
        
        # Hyperparameters for convergence detection
        # PATIENCE: Number of checks (every 5-10s) without a new record low
        PATIENCE_LIMIT = 360  # ~30 to 45 minutes of stagnation
        SMOOTHING_WINDOW = 20 # Number of samples for the moving average
        MIN_DELTA = 0.0005    # The minimum improvement required to reset patience

        # Initialize internal monitoring state per-voice
        if voice_name not in self._early_stopping_stats:
            self._early_stopping_stats[voice_name] = {
                "history": [],
                "best_avg": float('inf'),
                "patience_counter": 0
            }
        
        stats = self._early_stopping_stats[voice_name]
        
        # Maintain a rolling window of recent loss values
        stats["history"].append(current_loss)
        if len(stats["history"]) > SMOOTHING_WINDOW:
            stats["history"].pop(0)
        
        # Don't make any decisions until we have a full smoothing window
        if len(stats["history"]) < SMOOTHING_WINDOW:
            return

        # Use the Moving Average (MA) to avoid tripping on a single noisy spike
        current_avg = sum(stats["history"]) / len(stats["history"])
        
        # Compare current MA against the best MA seen so far
        if current_avg < (stats["best_avg"] - MIN_DELTA):
            # Significant improvement detected
            stats["best_avg"] = current_avg
            stats["patience_counter"] = 0
            # Optional: Log large improvements
        else:
            # Loss is stagnant or increasing
            stats["patience_counter"] += 1
            
            # Log progress every ~5 minutes to keep the console informative
            if stats["patience_counter"] % 60 == 0:
                logger.info(f"Early Stopping Monitor ({voice_name}): {stats['patience_counter']}/{PATIENCE_LIMIT} intervals without improvement (Current Avg: {current_avg:.4f}, Best: {stats['best_avg']:.4f})")

            # Final trigger: Stop the training process
            if stats["patience_counter"] >= PATIENCE_LIMIT:
                logger.info(f"EARLY STOPPING TRIGGERED for {voice_name}. Converged at loss {stats['best_avg']:.4f}")
                self.stop_training(voice_name)
                self._early_stopped_voices.add(voice_name)

# Singleton initialization
# This allows other modules (like the API) to import and use the instance immediately
training_manager = TrainingManager()
