import os
import sys
import time
import json
import re
import threading
import subprocess
import shutil
import urllib.request
import urllib.error
import webbrowser
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Common utilities for sanitization and config management
from common_utils import validate_voice_name, safe_config_save, safe_config_load

import tkinter as tk
from tkinter import ttk, messagebox
import audio_playback

# --- Constants & Paths ---
# Root directory of the project
ROOT_DIR = Path(__file__).resolve().parent.parent
# Location where Piper training "dojos" are stored
DOJO_ROOT = ROOT_DIR / "training" / "make piper voice models" / "tts_dojo"
# Name of the Docker container used for training
CONTAINER_NAME = "textymcspeechy-piper"
# URL for the Piper server to test-speak generated models
DEFAULT_PIPER_SERVER_URL = os.environ.get("PIPER_SERVER_URL", "http://127.0.0.1:5002")

# --- Logging Setup ---
LOGS_DIR = ROOT_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

log_file = LOGS_DIR / "training_dashboard.log"
error_log_file = LOGS_DIR / "errors.log"

# Detailed formatter for files
detailed_formatter = logging.Formatter("%(asctime)s [%(levelname)s] [%(name)s] %(message)s")

# Main log handler
main_handler = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=3)
main_handler.setLevel(logging.INFO)
main_handler.setFormatter(detailed_formatter)

# Shared error log handler
error_handler = RotatingFileHandler(error_log_file, maxBytes=5*1024*1024, backupCount=3)
error_handler.setLevel(logging.ERROR)
error_handler.setFormatter(detailed_formatter)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    handlers=[main_handler, error_handler]
)

logger = logging.getLogger("training_dashboard")


def _load_global_defaults() -> dict:
    """
    Load shared configuration defaults from src/config.json.
    This allows the dashboard to use the same language and prefix settings
    as the rest of the application.
    """
    cfg_path = ROOT_DIR / "src" / "config.json"
    if not cfg_path.exists():
        return {}

    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        return cfg if isinstance(cfg, dict) else {}
    except (json.JSONDecodeError, OSError):
        # Configuration file is missing or corrupted
        return {}
    except Exception:
        # Unexpected error (e.g. permission issues)
        return {}

class TrainingDashboardUI:
    """Main UI class for monitoring and managing Piper voice training."""
    
    def __init__(self, root):
        self.root = root
        self.root.title("Piper Training Dashboard")
        self.root.geometry("1000x900") # Larger initial size
        self.root.minsize(900, 750)
        
        # Force window to front on launch - use multiple methods for reliability
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.update()
        self.root.focus_force()
        self.root.after(100, lambda: [
            self.root.attributes("-topmost", False),
            self.root.focus_set()
        ])

        # --- Dashboard State variables (Tkinter variables for UI updates) ---
        self.selected_dojo = tk.StringVar()
        self.status_msg = tk.StringVar(value="Select a Dojo to begin")
        self.epoch_msg = tk.StringVar(value="Current Epoch: --")
        self.session_start_msg = tk.StringVar(value="Session Start: --")
        self.avg_time_msg = tk.StringVar(value="Avg. time per epoch: --:--")
        self.last_saved_msg = tk.StringVar(value="Last saved: None")
        self.disk_space_msg = tk.StringVar(value="Disk Space: -- GB")
        self.test_model_msg = tk.StringVar(value="No exported model found")
        self.test_text = tk.StringVar(value="Piper is a fast, local neural text to speech system.")
        self.auto_save_enabled = tk.BooleanVar(value=True)
        self.limit_saves = tk.BooleanVar(value=True)  # Storage management toggle
        self.deep_cleanup = tk.BooleanVar(value=True) # Free memory on stop
        self.keep_amount = tk.IntVar(value=1)  # Keep X most recent
        self.save_interval = tk.IntVar(value=10)
        self.checkpoints_counter = 0
        
        # --- New Config State (for initializing new training dojos) ---
        self.base_model_gender = tk.StringVar(value="M") # M or F
        self.quality_level = tk.StringVar(value="Medium") # Low, Medium, High
        self.needs_config = False # True if dataset.conf is missing

        # Optional per-voice language overrides (default to src/config.json)
        defaults = _load_global_defaults()
        self.espeak_language = tk.StringVar(value=(defaults.get("default_espeak_language") or "en-us").strip())
        self.piper_filename_prefix = tk.StringVar(value=(defaults.get("default_piper_filename_prefix") or "en_US").strip())
        
        # --- Timing & Tracking state ---
        self.first_checkpoint_time = None
        self.checkpoints_seen_count = 0
        self.last_checkpoint_epoch = -1
        self.piper_step = 5 # How many epochs per 'step' in Piper logs
        
        # --- Monitoring control ---
        self.is_monitoring = False
        self.monitoring_thread = None
        
        # Initialize UI and populate Dojo list
        self.setup_ui()
        self.refresh_dojos()

    def select_dojo(self, dojo_name: str) -> None:
        """
        Force select a specific dojo by name. 
        Appends '_dojo' suffix if missing and ensures it exists on disk.
        """
        dojo_name = (dojo_name or "").strip()
        if not dojo_name:
            return

        # Ensure suffix exists
        if not dojo_name.endswith("_dojo"):
            dojo_name = f"{dojo_name}_dojo"

        # Only select if the directory actually exists
        try:
            if (DOJO_ROOT / dojo_name).exists():
                self.selected_dojo.set(dojo_name)
                self.on_dojo_selected()
        except Exception:
            pass

    def setup_ui(self):
        """Assembles the Tkinter user interface components."""
        # Create a scrollable main container
        container = ttk.Frame(self.root)
        container.pack(fill="both", expand=True)

        canvas = tk.Canvas(container)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        window_id = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        
        # Handle canvas resizing to fill frame width
        def _on_canvas_configure(event):
            canvas.itemconfig(window_id, width=event.width)
        canvas.bind("<Configure>", _on_canvas_configure)

        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        # Top Frame - Selection & Basic Info
        top_frame = ttk.Frame(scrollable_frame, padding="10")
        top_frame.pack(fill="x")
        
        ttk.Label(top_frame, text="Dojo:", font=("Segoe UI", 10, "bold")).pack(side="left", padx=5)
        self.dojo_combo = ttk.Combobox(top_frame, textvariable=self.selected_dojo, state="readonly")
        self.dojo_combo.pack(side="left", padx=5, fill="x", expand=True)
        self.dojo_combo.bind("<<ComboboxSelected>>", self.on_dojo_selected)
        
        self.start_btn = ttk.Button(top_frame, text="Start Training", command=self.start_training_confirm, state="disabled")
        self.start_btn.pack(side="left", padx=5)

        ttk.Button(top_frame, text="Refresh", command=self.refresh_dojos).pack(side="left", padx=5)
        ttk.Button(top_frame, text="📦 Manage Storage", command=self.open_storage_manager).pack(side="left", padx=5)
        ttk.Button(top_frame, text="🚀 Open Web UI", command=self.open_web_dashboard).pack(side="left", padx=5)
        ttk.Label(top_frame, textvariable=self.disk_space_msg, foreground="#555").pack(side="right", padx=15)

        # Main Content container split into two columns
        main_content = ttk.Frame(scrollable_frame, padding="10")
        main_content.pack(fill="both", expand=True)

        # Left Column: Statistics & Action Buttons
        left_col = ttk.Frame(main_content)
        left_col.pack(side="left", fill="both", expand=True, padx=(0, 10))

        # Training Progress Status Pane
        status_frame = ttk.LabelFrame(left_col, text=" Training Progress ", padding="15")
        status_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(status_frame, textvariable=self.status_msg, font=("Segoe UI", 12, "bold"), foreground="#2c3e50").pack(pady=2)
        
        # Grid layout for specific training statistics
        stats_grid = ttk.Frame(status_frame)
        stats_grid.pack(fill="x", pady=5)
        
        ttk.Label(stats_grid, textvariable=self.epoch_msg, font=("Segoe UI", 10, "bold")).grid(row=0, column=0, padx=10, sticky="w")
        ttk.Label(stats_grid, textvariable=self.session_start_msg, font=("Segoe UI", 10)).grid(row=0, column=1, padx=10, sticky="w")
        ttk.Label(stats_grid, textvariable=self.avg_time_msg, font=("Segoe UI", 10)).grid(row=1, column=0, padx=10, sticky="w")
        ttk.Label(stats_grid, textvariable=self.last_saved_msg, font=("Segoe UI", 10), foreground="#27ae60").grid(row=1, column=1, padx=10, sticky="w")

        # Manual Manual Actions Pane (Save, Tensorboard, Stop)
        actions_frame = ttk.LabelFrame(left_col, text=" Manual Actions ", padding="15")
        actions_frame.pack(fill="x", pady=(0, 10))
        
        self.save_btn = ttk.Button(actions_frame, text="SAVE & EXPORT CURRENT CHECKPOINT", width=40, command=self.manual_save, state="disabled")
        self.save_btn.pack(pady=(10, 2))
        
        storage_frame = ttk.Frame(actions_frame)
        storage_frame.pack(pady=(0, 10))
        
        ttk.Checkbutton(storage_frame, text="Limit saves to last: ", variable=self.limit_saves).pack(side="left")
        self.keep_spin = ttk.Spinbox(storage_frame, from_=1, to=100, textvariable=self.keep_amount, width=3)
        self.keep_spin.pack(side="left", padx=2)
        ttk.Label(storage_frame, text=" version(s)").pack(side="left")

        # Container for Tensorboard and Stop buttons
        control_frame = ttk.Frame(actions_frame)
        control_frame.pack(fill="x", pady=5)
        
        self.tb_btn = ttk.Button(control_frame, text="Open TensorBoard", command=self.open_tensorboard)
        self.tb_btn.pack(side="left", expand=True, padx=5)
        
        self.open_dojo_btn = ttk.Button(control_frame, text="📁 Open Dojo Folder", command=self.open_dojo_folder)
        self.open_dojo_btn.pack(side="left", expand=True, padx=5)
        
        self.stop_btn = ttk.Button(control_frame, text="Stop Training", command=self.stop_training)
        self.stop_btn.pack(side="left", expand=True, padx=5)

        ttk.Checkbutton(actions_frame, text="Deep Cleanup (Free RAM on stop)", variable=self.deep_cleanup).pack(pady=2)
        
        # Voice Tester Pane for trying out the latest model
        test_frame = ttk.LabelFrame(left_col, text=" Voice Tester ", padding="15")
        test_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(test_frame, textvariable=self.test_model_msg, foreground="#555", wraplength=350, font=("Segoe UI", 9)).pack(fill="x", pady=5)
        
        input_frame = ttk.Frame(test_frame)
        input_frame.pack(fill="x", pady=5)
        
        entry = ttk.Entry(input_frame, textvariable=self.test_text)
        entry.pack(side="left", fill="x", expand=True, padx=(0, 5))

        self.speak_btn = ttk.Button(input_frame, text="▶ Speak", width=10, command=self.speak_current_model, state="disabled")
        self.speak_btn.pack(side="right")

        export_frame = ttk.Frame(test_frame)
        export_frame.pack(fill="x", pady=(5, 0))
        self.export_prod_btn = ttk.Button(
            export_frame,
            text="Export to Piper voices",
            command=self.export_current_model_to_production,
            state="disabled",
        )
        self.export_prod_btn.pack(fill="x")
        
        # Automatic Saving Configuration Pane
        auto_frame = ttk.LabelFrame(left_col, text=" Auto-Save Settings ", padding="15")
        auto_frame.pack(fill="x")
        
        ttk.Checkbutton(auto_frame, text="Enable Automatic Saving", variable=self.auto_save_enabled).pack(anchor="w", pady=5)
        
        interval_frame = ttk.Frame(auto_frame)
        interval_frame.pack(fill="x", pady=5)
        ttk.Label(interval_frame, text="Save every:").pack(side="left")
        self.interval_spin = ttk.Spinbox(interval_frame, from_=1, to=100, textvariable=self.save_interval, width=5)
        self.interval_spin.pack(side="left", padx=5)
        ttk.Label(interval_frame, text="checkpoints seen").pack(side="left")

        # Right Column: System Log / Event Console
        log_frame = ttk.LabelFrame(main_content, text=" System Event Log ", padding="5")
        log_frame.pack(side="right", fill="both", expand=True)
        
        self.log_text = tk.Text(log_frame, background="#1e1e1e", foreground="#d4d4d4", font=("Consolas", 9), insertbackground="white")
        self.log_text.pack(fill="both", expand=True)

        # Log Control Buttons
        log_ctrls = ttk.Frame(log_frame)
        log_ctrls.pack(anchor="e", pady=2)
        
        ttk.Button(log_ctrls, text="📋 Copy", width=8, command=self.copy_log).pack(side="left", padx=2)
        ttk.Button(log_ctrls, text="🗑 Clear", width=8, command=lambda: self.log_text.delete("1.0", tk.END)).pack(side="left", padx=2)
        
        # Footer Progress Bar (used during long-running tasks like exports)
        self.progress = ttk.Progressbar(self.root, mode="indeterminate")
        self.progress.pack(fill="x", side="bottom")

    def open_storage_manager(self):
        """Launches the dedicated storage management tool."""
        script_path = ROOT_DIR / "src" / "storage_manager_ui.py"
        try:
            # Run using the same python executable
            subprocess.Popen([sys.executable, str(script_path)])
        except Exception as e:
            messagebox.showerror("Error", f"Could not launch Storage Manager: {e}")

    def open_web_dashboard(self):
        """Opens the HTML5 Web Dashboard in the default browser."""
        try:
            webbrowser.open(DEFAULT_PIPER_SERVER_URL)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open browser: {e}")

    def on_dojo_selected(self, event=None):
        """Called when a user selects a Dojo from the dropdown."""
        dojo = self.selected_dojo.get()
        if not dojo: return
        
        # Define paths for the specific dojo
        self.dojo_path = DOJO_ROOT / dojo
        # Path where PyTorch Lightning saves training checkpoints
        self.checkpoints_dir = self.dojo_path / "training_folder" / "lightning_logs" / "version_0" / "checkpoints"
        # Path where we save exported .onnx models
        self.save_dir = self.dojo_path / "voice_checkpoints"
        self.voices_dir = self.dojo_path / "tts_voices"
        
        # Reset training/monitoring session counters
        self.checkpoints_seen_count = 0
        self.first_checkpoint_time = None
        self.last_checkpoint_epoch = -1
        self.checkpoints_counter = 0
        
        # Load Piper Step & other persistent settings from the dojo directory if they exist
        self.load_settings()
        
        self.log(f"Dashboard monitoring: {dojo}", "info")
        self.is_monitoring = True
        self.save_btn.config(state="normal")
        self.start_btn.config(state="normal")
        
        # Verify if the dojo is configured and ready for training
        self.check_configuration(dojo)

        # Look for the most recently exported model for the Voice Tester
        self.find_latest_model()
        
        # Ensure the background monitoring loop is running
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            pass # Thread is already active
        else:
            self.monitoring_thread = threading.Thread(target=self.monitor_loop, daemon=True)
            self.monitoring_thread.start()

    def check_configuration(self, dojo_name):
        """
        Checks if the dojo has the required configuration files to start training.
        If files are missing or empty, sets needs_config to True.
        """
        # Look for dataset.conf in dataset folder
        dojo_path = DOJO_ROOT / dojo_name
        dataset_path = dojo_path / "dataset"
        conf_path = dataset_path / "dataset.conf"
        # Also check target_voice_dataset for .QUALITY file (required by run_training.sh)
        quality_path = dojo_path / "target_voice_dataset" / ".QUALITY"
        target_conf_path = dojo_path / "target_voice_dataset" / "dataset.conf"

        def _nonempty(path: Path) -> bool:
            """Checks if a file exists and contains data."""
            try:
                return path.exists() and path.is_file() and path.stat().st_size > 0
            except Exception:
                return False

        # All three of these are critical for the training scripts to function
        conf_ok = _nonempty(conf_path)
        quality_ok = _nonempty(quality_path)
        target_conf_ok = _nonempty(target_conf_path)
        
        if (not conf_ok) or (not quality_ok) or (not target_conf_ok):
            self.needs_config = True
            self.status_msg.set("Configuration Required (Click Start to Configure)")
        else:
            self.needs_config = False
            self.status_msg.set("Ready to start.")
            # Attempt to parse gender and language settings from the existing config
            try:
                txt = conf_path.read_text(encoding='utf-8')
                if 'DEFAULT_VOICE_TYPE="F"' in txt or 'DEFAULT_VOICE_TYPE="female"' in txt:
                    self.base_model_gender.set("F")
                else: 
                    self.base_model_gender.set("M")

                # Parse language/prefix overrides if they were manually added to the conf
                m_lang = re.search(r'ESPEAK_LANGUAGE_IDENTIFIER=["\']?([^"\'\r\n]+)["\']?', txt)
                if m_lang:
                    self.espeak_language.set(m_lang.group(1).strip())
                m_pref = re.search(r'PIPER_FILENAME_PREFIX=["\']?([^"\'\r\n]+)["\']?', txt)
                if m_pref:
                    self.piper_filename_prefix.set(m_pref.group(1).strip())
            except: pass

    def show_config_dialog(self, dojo_name):
        """
        Displays a popup window to configure a new voice dojo.
        Asks for:
        - Base Model Gender: Used to pick a starting point for finetuning.
        - Quality Level: Sets the sampling rate and model complexity.
        - Language Settings: Espeak identifier and file naming prefix.
        """
        popup = tk.Toplevel(self.root)
        popup.title("Configure Voice")
        popup.geometry("450x550") # Larger initial size to avoid scrolling
        popup.minsize(400, 450)
        
        # Add scrollable container
        container = ttk.Frame(popup)
        container.pack(fill="both", expand=True)

        canvas = tk.Canvas(container)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        window_id = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        
        # Handle canvas resizing to fill frame width
        def _on_canvas_configure(event):
            canvas.itemconfig(window_id, width=event.width)
        canvas.bind("<Configure>", _on_canvas_configure)

        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        # --- Voice Properties ---
        ttk.Label(scrollable_frame, text="Base Voice Model:", font=("", 10, "bold")).pack(pady=(10,5))
        ttk.Radiobutton(scrollable_frame, text="Male (Masculine)", variable=self.base_model_gender, value="M").pack(anchor="center")
        ttk.Radiobutton(scrollable_frame, text="Female (Feminine)", variable=self.base_model_gender, value="F").pack(anchor="center")
        
        ttk.Label(scrollable_frame, text="Quality Level:", font=("", 10, "bold")).pack(pady=(15,5))
        ttk.Combobox(scrollable_frame, textvariable=self.quality_level, values=["Low", "Medium", "High"], state="readonly").pack(pady=5)

        # --- Advanced Language Overrides ---
        adv = ttk.LabelFrame(scrollable_frame, text=" Advanced: Language ", padding=10)
        adv.pack(fill="x", padx=10, pady=(15, 5))

        ttk.Label(adv, text="Espeak language (e.g. en-us):").pack(anchor="w")
        ttk.Entry(adv, textvariable=self.espeak_language).pack(fill="x", pady=(2, 8))

        ttk.Label(adv, text="Piper filename prefix (e.g. en_US):").pack(anchor="w")
        ttk.Entry(adv, textvariable=self.piper_filename_prefix).pack(fill="x", pady=(2, 0))
        
        def save_and_start():
            """Generates configs, closes the popup, and kicks off training."""
            self.generate_configs(dojo_name)
            popup.destroy()
            threading.Thread(target=self.run_training_process, args=(dojo_name,), daemon=True).start()
            
        ttk.Button(scrollable_frame, text="Save & Start Training", command=save_and_start).pack(pady=20)

    def generate_configs(self, dojo_name):
        """
        Creates the necessary configuration and marker files for the Piper training scripts.
        This includes dataset.conf, .QUALITY, .SAMPLING_RATE, etc.
        """
        dojo_path = DOJO_ROOT / dojo_name
        dataset_path = dojo_path / "dataset"
        if not dataset_path.exists():
            dataset_path.mkdir(parents=True, exist_ok=True)
            
        conf_path = dataset_path / "dataset.conf"
        
        gender = self.base_model_gender.get()
        quality = self.quality_level.get()
        
        self.log(f"Generating config: Gender={gender}, Quality={quality}")
        
        # --- Mapping Quality to codes (L, M, H) ---
        q_map = {"Low": "L", "Medium": "M", "High": "H"}
        q_code = q_map.get(quality, "M")
        
        # Ensure key folders required by the linux scripts exist
        target_dataset_path = dojo_path / "target_voice_dataset"
        target_dataset_path.mkdir(parents=True, exist_ok=True)
        scripts_path = dojo_path / "scripts"
        scripts_path.mkdir(parents=True, exist_ok=True)

        # --- Writing .QUALITY and .SCRATCH files ---
        # .QUALITY tells the training scripts which model depth to use.
        # .SCRATCH tells it whether to finetune (false) or start fresh (true).
        for p in (dataset_path, target_dataset_path):
            try:
                with open(p / ".QUALITY", "w", encoding="utf-8", newline="\n") as f:
                    f.write(f"{q_code}\n")
            except Exception as e:
                self.log(f"Error writing to {p.name}/.QUALITY: {e}", "warning")

            try:
                with open(p / ".SCRATCH", "w", encoding="utf-8", newline="\n") as f:
                    f.write("false\n")
            except Exception as e:
                self.log(f"Error writing to {p.name}/.SCRATCH: {e}", "warning")
        
        # --- Writing .SAMPLING_RATE and .MAX_WORKERS to scripts/ ---
        # Required by the preprocessing script to resample audio and parallelize phonemization.
        try:
            sample_rate = "22050" 
            if quality == "Low": sample_rate = "16000"
            with open(scripts_path / ".SAMPLING_RATE", "w", encoding="utf-8", newline='\n') as f:
                f.write(f"{sample_rate}\n")

            # Determine safer max workers: Piper preprocess crashes if batch_size (total/workers*2) < 1
            # We count files in the dataset to gauge a safe worker limit for this run.
            num_wavs = len(list(dataset_path.glob("*.wav")))
            workers = 4
            if num_wavs > 0 and num_wavs < 8:
                workers = 1 # Force single worker for tiny datasets to avoid division error
                self.log(f"Tiny dataset detected ({num_wavs} files). Using 1 worker for stability.", "info")

            with open(scripts_path / ".MAX_WORKERS", "w", encoding="utf-8", newline='\n') as f:
                f.write(f"{workers}\n")
        except Exception as e:
            self.log(f"Error writing to scripts/ files: {e}", "warning")

        # --- Creating dataset.conf ---
        # This is the main configuration file read by the bash scripts.
        defaults = _load_global_defaults()
        espeak_lang = (self.espeak_language.get() or defaults.get("default_espeak_language") or "en-us").strip()
        piper_prefix = (self.piper_filename_prefix.get() or defaults.get("default_piper_filename_prefix") or "en_US").strip()

        content = f"""# Auto-generated by PiperTTS Mockingbird Dashboard
NAME="{dojo_name.replace('_dojo','')}"
DESCRIPTION="Custom voice"
DEFAULT_VOICE_TYPE="{gender}"
LOW_AUDIO="wav_16000"
MEDIUM_AUDIO="wav_22050"
HIGH_AUDIO="wav_22050"
ESPEAK_LANGUAGE_IDENTIFIER="{espeak_lang}"
PIPER_FILENAME_PREFIX="{piper_prefix}"
"""
        try:
            with open(conf_path, "w", encoding='utf-8', newline='\n') as f:
                f.write(content)
            
            # Also write to target_voice_dataset/dataset.conf (shadow copy for consistency)
            target_conf_path = dojo_path / "target_voice_dataset" / "dataset.conf"
            if target_conf_path.parent.exists():
                 with open(target_conf_path, "w", encoding='utf-8', newline='\n') as f:
                    f.write(content)

        except Exception as e:
            self.log(f"Error writing conf: {e}", "error")
            
        # --- Linking pretrained checkpoint ---
        # Final step is to provide a base model to finetune from.
        self.link_pretrained_checkpoint(dojo_name)

    def link_pretrained_checkpoint(self, dojo_name):
        """Locates and copies the appropriate pretrained checkpoint into the dojo."""
        dojo_path = DOJO_ROOT / dojo_name
        gender = self.base_model_gender.get() # M or F
        quality = self.quality_level.get().lower() # low, medium, high
        
        gender_dir = "F_voice" if gender == "F" else "M_voice"
        checkpoint_src_dir = DOJO_ROOT / "PRETRAINED_CHECKPOINTS" / "default" / gender_dir / quality
        dest_dir = dojo_path / "pretrained_tts_checkpoint"
        
        if not checkpoint_src_dir.exists():
            self.log(f"Pretrained source folder missing: {checkpoint_src_dir}", "warning")
            return
            
        ckpts = list(checkpoint_src_dir.glob("*.ckpt"))
        if not ckpts:
            self.log(f"No .ckpt files found in {checkpoint_src_dir}. Training will start from scratch.", "warning")
            return
            
        src_ckpt = ckpts[0]
        dest_dir.mkdir(parents=True, exist_ok=True)
        
        # Remove existing files/links to avoid clutter
        for item in dest_dir.glob("*.ckpt"):
            try:
                if item.is_symlink() or item.is_file(): item.unlink()
            except: pass
            
        dest_ckpt = dest_dir / src_ckpt.name
        self.log(f"Linking pretrained checkpoint: {src_ckpt.name}...")
        
        try:
            # We copy instead of symlink to avoid Windows privilege issues
            shutil.copy2(src_ckpt, dest_ckpt)
            self.log(f"Successfully prepared pretrained checkpoint.", "success")
        except Exception as e:
            self.log(f"Failed to copy checkpoint: {e}", "error")

    def start_training_confirm(self):
        """
        [STEP 5] AUTO-TRAIN FLOW: Start Training Confirmation
        
        This is the "Start" button on the dashboard.
        1. Checks if the specific dojo needs configuration (dataset.conf).
        2. Asks for final confirmation.
        3. Spawns the `run_training_process` thread (background) to:
           - Start Docker if needed.
           - Open the visible terminal window (Step 6).
        """
        dojo = self.selected_dojo.get()
        if not dojo: return

        if self.needs_config:
            self.show_config_dialog(dojo)
            return
        
        if messagebox.askyesno("Start Training", f"Start training session for '{dojo}'?\n\n"
                                               f"IMPORTANT: By starting, you confirm you have consent from the voice owner.\n\n"
                                               f"This will launch the training process inside the Docker container."):
            # [UX IMPROVEMENT] Ensure configs reflect current UI state (Gender, Quality, etc.) 
            # This handles the case where a user changes a setting on the dashboard 
            # and immediately hits 'Start' without a separate save.
            self.generate_configs(dojo)
            threading.Thread(target=self.run_training_process, args=(dojo,), daemon=True).start()

    def run_training_process(self, dojo_name):
        """
        The main worker thread for starting the training session.
        This function handles Docker lifecycle and launches the training terminal.
        """
        self.log(f"Initiating training for {dojo_name}...", "info")

        # --- Preflight Configuration Check ---
        # Ensure dojo config files exist and are non-empty.
        # Some flows create placeholder zero-byte dataset.conf files; that breaks preprocessing.
        try:
            dojo_path = DOJO_ROOT / dojo_name
            conf1 = dojo_path / "dataset" / "dataset.conf"
            conf2 = dojo_path / "target_voice_dataset" / "dataset.conf"
            quality = dojo_path / "target_voice_dataset" / ".QUALITY"

            def _nonempty(path: Path) -> bool:
                try:
                    return path.exists() and path.is_file() and path.stat().st_size > 0
                except Exception:
                    return False

            if (not _nonempty(conf1)) or (not _nonempty(conf2)) or (not _nonempty(quality)):
                self.log("Detected missing/empty dojo config; regenerating now...", "warning")
                self.generate_configs(dojo_name)
        except Exception as e:
            self.log(f"Config preflight warning: {e}", "warning")

        # --- Phase 1: Docker Container Management ---
        try:
            # Check if our target container is already running
            check_cmd = ["docker", "ps", "--format", "{{.Names}}"]
            creation_flags = 0
            if os.name == 'nt':
                creation_flags = subprocess.CREATE_NO_WINDOW # Run background docker checks silently
                
            result = subprocess.run(check_cmd, capture_output=True, text=True, creationflags=creation_flags)
            
            if CONTAINER_NAME not in result.stdout:
                self.log(f"Container {CONTAINER_NAME} is not running. Attempting to start...", "warning")
                
                # Try simple 'docker start' first (case where it's created but stopped)
                start_res = subprocess.run(["docker", "start", CONTAINER_NAME], capture_output=True, text=True, creationflags=creation_flags)
                
                if start_res.returncode != 0:
                    # If 'docker start' failed (e.g. no such container), try running the setup script
                    self.log("Container does not exist or cannot be started. Creating new instance...", "warning")
                    
                    # Point to run_container.ps1 which handles full setup (pulling image, creating container)
                    voice_models_dir = ROOT_DIR / "training" / "make piper voice models"
                    script_path = voice_models_dir / "run_container.ps1"
                    
                    if not script_path.exists():
                        self.log(f"Cannot find startup script at {script_path}", "error")
                        return

                    # Construct PowerShell command to run the setup script
                    ps_cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script_path)]
                    
                    self.log("Running setup script... this may take a moment...", "info")
                    
                    try:
                        # Run the setup script in the correct working directory
                        setup_res = subprocess.run(
                            ps_cmd, 
                            cwd=str(voice_models_dir),
                            capture_output=True, 
                            text=True, 
                            creationflags=creation_flags
                        )
                        
                        if setup_res.returncode != 0:
                            self.log(f"Setup script failed: {setup_res.stderr}", "error")
                            self.log(f"Output: {setup_res.stdout[:500]}", "info")
                            return
                            
                    except Exception as e:
                        self.log(f"Failed to run setup script: {e}", "error")
                        return

                    # [OPTIMIZATION] Polling wait for the container to stabilize
                    self.log("Waiting for container to initialize...", "info")
                    container_ready = False
                    for _ in range(15): # Wait up to 30 seconds
                        time.sleep(2)
                        check_res = subprocess.run(check_cmd, capture_output=True, text=True, creationflags=creation_flags)
                        if CONTAINER_NAME in check_res.stdout:
                            container_ready = True
                            break
                    
                    if not container_ready:
                         self.log("Container failed to start after setup script.", "error")
                         return

                else:
                    time.sleep(3) # Wait for startup if simple start worked

                self.log("Container started successfully.", "success")
            else:
                self.log("Container is already running.", "info")
                
        except Exception as e:
            self.log(f"Docker check failed: {e}", "error")
            return

        # --- Phase 2: Launching Training Terminal ---
        # Construct the command to run inside the Linux container via docker exec
        # 'run_training.sh' is the entry point for the Piper training bash scripts.
        import shlex
        dojo_path_in_container = f"/app/tts_dojo/{dojo_name}"
        docker_cmd = f"cd {shlex.quote(dojo_path_in_container)} && bash run_training.sh"
        
        # Wrap it in a PowerShell command that opens a NEW visible terminal window
        # -NoExit keeps the window open so they can see the final status/errors
        ps_cmd_str = f'docker exec -it {CONTAINER_NAME} bash -lc "{docker_cmd}"'
        
        self.log(f"Launching interactive terminal for {dojo_name}...", "info")
        
        try:
            full_cmd = ["powershell", "-NoExit", "-Command", ps_cmd_str]
            
            # CREATE_NEW_CONSOLE ensures a visible window pops up on Windows
            flags = 0
            if os.name == 'nt':
                flags = subprocess.CREATE_NEW_CONSOLE
                
            subprocess.Popen(full_cmd, creationflags=flags)
            
            self.log("Interactive training terminal launched.", "success")
            self.root.after(0, lambda: self.status_msg.set("Training Terminal Opened"))
                
        except Exception as e:
            self.log(f"Failed to launch training terminal: {e}", "error")
                
        except Exception as e:
            self.log(f"Execution error: {e}", "error")

    def open_tensorboard(self):
        import webbrowser
        self.log("Opening TensorBoard at http://localhost:6006", "info")
        webbrowser.open("http://localhost:6006")

    def open_dojo_folder(self):
        """Opens the active Dojo directory in the system file explorer."""
        if not hasattr(self, 'dojo_path') or not self.dojo_path.exists():
            messagebox.showerror("Error", "No dojo selected or folder missing.")
            return
            
        try:
            if os.name == 'nt':
                os.startfile(str(self.dojo_path))
            else:
                opener = "open" if sys.platform == "darwin" else "xdg-open"
                subprocess.Popen([opener, str(self.dojo_path)])
        except Exception as e:
            self.log(f"Failed to open folder: {e}", "error")

    def stop_training(self):
        """
        Signals the Docker container to stop.
        This is a 'clean' shutdown: Docker sends SIGTERM to the processes inside,
        allowing PyTorch Lightning/Piper to save a final checkpoint before exiting.
        """
        if messagebox.askyesno("Stop Training", "Are you sure you want to stop the training process?"):
            def work():
                try:
                    self.log("Stopping training container...", "warning")
                    self.root.after(0, lambda: self.status_msg.set("Stopping container..."))
                    self.root.after(0, lambda: self.progress.start())
                    
                    # Run 'docker stop' and wait for it to complete
                    result = subprocess.run(["docker", "stop", CONTAINER_NAME], 
                                          capture_output=True, text=True, timeout=30)
                    
                    if result.returncode == 0:
                        self.log("Stop signal sent and container stopped successfully.", "success")
                        
                        # Apply Deep Cleanup if requested (Essential for 'potatoes' on Windows)
                        if self.deep_cleanup.get():
                            try:
                                self.log("Performing Deep Cleanup to reclaim memory...", "info")
                                subprocess.run(["docker", "system", "prune", "-f"], 
                                             capture_output=True, text=True, timeout=30)
                                if os.name == 'nt':
                                    self.log("Shutting down WSL (Killing VmmemWSL memory hog)...", "warning")
                                    # This is the heavy hitter that clears the 1.5GB+ usage
                                    subprocess.run(["wsl.exe", "--shutdown"], 
                                                 capture_output=True, text=True, timeout=30)
                                    self.log("Deep Cleanup complete. Memory reference cleared.", "success")
                            except Exception as cleanup_err:
                                self.log(f"Deep cleanup failed: {cleanup_err}", "error")

                        self.root.after(0, lambda: self.status_msg.set("Training Stopped"))
                    else:
                        self.log(f"Error stopping container: {result.stderr}", "error")
                        self.root.after(0, lambda: self.status_msg.set("Stop failed (check log)"))
                        
                except Exception as e:
                    self.log(f"Error stopping training: {e}", "error")
                finally:
                    self.root.after(0, lambda: self.progress.stop())

            threading.Thread(target=work, daemon=True).start()

    def log(self, text, type="info"):
        """
        Helper to append a message to the UI's 'System Event Log'.
        Includes timestamping and color-coding based on the message type.
        This method is thread-safe.
        """
        def _execute():
            timestamp = time.strftime("%H:%M:%S")
            color = "#d4d4d4" # Default light grey
            if type == "error": color = "#f44336"   # Red
            if type == "success": color = "#4caf50" # Green
            if type == "warning": color = "#ff9800" # Orange
            
            # Configure the tag for the specific message color
            self.log_text.tag_config(type, foreground=color)
            self.log_text.insert(tk.END, f"[{timestamp}] ", type)
            self.log_text.insert(tk.END, f"{text}\n", type)
            self.log_text.see(tk.END) # Scroll to bottom

        self.root.after(0, _execute)

    def copy_log(self):
        """Copies the contents of the system log to the system clipboard."""
        try:
            content = self.log_text.get("1.0", tk.END)
            self.root.clipboard_clear()
            self.root.clipboard_append(content)
            self.log("Log copied to clipboard.", "info")
        except Exception as e:
            self.log(f"Failed to copy log: {e}", "error")

    def refresh_dojos(self):
        if not DOJO_ROOT.exists():
            self.log(f"Error: Dojo root not found at {DOJO_ROOT}", "error")
            return
        
        # Sort dojos alphabetically for a better user experience
        dojos = sorted([d.name for d in DOJO_ROOT.iterdir() if d.is_dir() and d.name.endswith("_dojo")])
        self.dojo_combo['values'] = dojos
        self.log(f"Found {len(dojos)} training dojos.")
        self.update_disk_space()

    def update_disk_space(self):
        try:
            total, used, free = shutil.disk_usage(ROOT_DIR)
            free_gb = free // (2**30)
            self.disk_space_msg.set(f"Free Space: {free_gb} GB")
        except:
            pass




    def load_settings(self):
        settings_path = self.dojo_path / "scripts" / "SETTINGS.txt"
        if settings_path.exists():
            try:
                content = settings_path.read_text()
                # Parse simple KEY=VALUE format
                match = re.search(r'PIPER_SAVE_CHECKPOINT_EVERY_N_EPOCHS=(\d+)', content)
                if match: self.piper_step = int(match.group(1))
                
                match = re.search(r'AUTO_SAVE_EVERY_NTH_CHECKPOINT_FILE=(\d+)', content)
                if match: self.save_interval.set(int(match.group(1)))
            except:
                pass

    def monitor_loop(self):
        """
        Background loop run in a separate thread.
        Periodically checks the training directory for new .ckpt files and updates stats.
        """
        last_newest = None
        seen_best = set()

        while self.is_monitoring:
            try:
                self.update_disk_space()
                if self.checkpoints_dir.exists():
                    # Look for all checkpoint files saved by PyTorch Lightning
                    ckpts = list(self.checkpoints_dir.glob("*.ckpt"))
                    if ckpts:
                        # Find the one most recently written to disk
                        newest = max(ckpts, key=lambda p: p.stat().st_mtime)
                        if newest != last_newest:
                            self.handle_new_checkpoint(newest)
                            last_newest = newest
                        
                        # ALSo verify if any new 'best-' checkpoint appeared that wasn't the absolute newest
                        # (This happens if standard + best save at almost same time)
                        for c in ckpts:
                            if (c.name.startswith("best-") or "best_" in c.name) and c.name not in seen_best:
                                self.handle_new_checkpoint(c)
                                seen_best.add(c.name)

                    else:
                        self.status_msg.set("Waiting for first checkpoint...")
                else:
                    self.status_msg.set("Waiting for training folder...")
            except Exception as e:
                self.log(f"Monitor error: {e}", "error")
            
            # Poll every 3 seconds to balance responsiveness and CPU usage
            time.sleep(3)

    def handle_new_checkpoint(self, path):
        """
        Updates the dashboard with information from a newly detected checkpoint file.
        Calculates training speed and manages auto-save logic.
        """
        filename = path.name
        self.status_msg.set(f"Latest File: {filename}")
        self.log(f"Checkpoint detected: {filename}", "info")
        
        # --- Extract current Epoch from filename (format: ...epoch=123-step=456.ckpt) ---
        match = re.search(r"epoch=(\d+)", filename)
        if match:
            current_epoch = int(match.group(1))
            self.epoch_msg.set(f"Current Epoch: {current_epoch}")
            
            # Record the epoch we started this session with to track progress within this run
            if self.last_checkpoint_epoch == -1:
                self.last_checkpoint_epoch = current_epoch
                self.session_start_msg.set(f"Session Start: Epoch {current_epoch}")
        
        # --- Training Speed Calculation ---
        now = time.time()
        if self.first_checkpoint_time is None:
            # This is the first file we've seen since opening the tab
            self.first_checkpoint_time = now
            self.checkpoints_seen_count = 1
        else:
            self.checkpoints_seen_count += 1
            # Total seconds elapsed since the first checkpoint arrived
            elapsed = now - self.first_checkpoint_time
            # Average time between checkpoint file arrivals
            avg_per_file = elapsed / (self.checkpoints_seen_count - 1)
            # Average time per SINGLE epoch (assuming piper_step epochs per file)
            avg_per_epoch = avg_per_file / self.piper_step
            
            mins = int(avg_per_epoch // 60)
            secs = int(avg_per_epoch % 60)
            self.avg_time_msg.set(f"Avg. time per epoch: {mins:02d}:{secs:02d}")

        # --- Automatic Saving logic ---
        # If enabled, only save every N checkpoints to avoid filling disk too quickly
        if self.auto_save_enabled.get():
            # Special case for "Best Quality" checkpoints (filename starts with 'best-')
            if filename.startswith("best-") or "best_" in filename:
                self.log(f"Auto-saving BEST checkpoint: {filename}", "success")
                self.perform_save(path)
            else:
                self.checkpoints_counter += 1
                if self.checkpoints_counter >= self.save_interval.get():
                    self.checkpoints_counter = 0
                    self.log(f"Auto-saving {filename} (interval met)", "success")
                    self.perform_save(path)

    def manual_save(self):
        ckpts = list(self.checkpoints_dir.glob("*.ckpt")) if self.checkpoints_dir.exists() else []
        if not ckpts:
            messagebox.showwarning("Wait", "No checkpoints available yet.")
            return
        
        newest = max(ckpts, key=lambda p: p.stat().st_mtime)
        self.log(f"Manual save triggered for: {newest.name}", "info")
        self.perform_save(newest)

    def perform_save(self, path):
        """
        Copies a .ckpt file from the active training folder to a persistent 'voice_checkpoints' folder.
        Runs in a background thread to prevent UI freezing.
        """
        filename = path.name
        target = self.save_dir / filename
        
        if target.exists():
            self.log(f"Already saved: {filename}", "warning")
            return

        def work():
            """Worker to handle the file copy and subsequent ONNX export."""
            try:
                # Show visual feedback while copying
                self.root.after(0, lambda: self.progress.start())
                self.save_dir.mkdir(exist_ok=True)
                
                # --- Safety check: Wait for file to finish writing ---
                # Checkpoints can be large; we wait until the file size stabilizes.
                last_size = -1
                while True:
                    current_size = path.stat().st_size
                    if current_size == last_size and current_size > 0:
                        break
                    last_size = current_size
                    time.sleep(2) # Reduced from 5s to 2s for better responsiveness

                # Safely copy the checkpoint
                shutil.copy2(path, target)
                self.log(f"Successfully saved {filename} to voice_checkpoints", "success")
                
                # --- STORAGE MANAGEMENT ---
                # If set to keep only X most recent, delete older checkpoints and voice folders
                if self.limit_saves.get():
                    keep = max(1, self.keep_amount.get()) # Ensure minimum of 1
                    
                    # 1. Cleanup Checkpoints
                    # Filter out "best" checkpoints so they are never auto-deleted by the history limit
                    all_ckpts = sorted(
                        [p for p in self.save_dir.glob("*.ckpt") if not p.name.startswith("best-")], 
                        key=lambda p: p.stat().st_mtime, reverse=True
                    )
                    
                    if len(all_ckpts) > keep:
                        to_delete = all_ckpts[keep:]
                        for old_ckpt in to_delete:
                            try:
                                old_ckpt.unlink()
                            except Exception: pass
                    
                    # 2. Cleanup Voice Folders
                    # We match folders like "voice_epoch" or "voice_step"
                    # Also protecting folders containing "_best_"
                    if self.voices_dir.exists():
                        all_voices = sorted(
                            [d for d in self.voices_dir.iterdir() if d.is_dir() and d.name != ".required_directory" and "_best_" not in d.name],
                            key=lambda d: d.stat().st_mtime,
                            reverse=True
                        )
                        if len(all_voices) > keep:
                            to_delete_voices = all_voices[keep:]
                            for old_folder in to_delete_voices:
                                try:
                                    shutil.rmtree(old_folder)
                                except Exception: pass
                    
                    self.log(f"Storage cleanup: Kept {keep} most recent versions.", "info")

                # --- AUTO-EXPORT ---
                # Once saved, immediately try to convert it to a runnable .onnx model
                self.trigger_export(filename)
                
            except Exception as e:
                self.log(f"Error saving {filename}: {e}", "error")
            finally:
                self.root.after(0, lambda: self.progress.stop())

        threading.Thread(target=work, daemon=True).start()

    def trigger_export(self, ckpt_filename):
        """
        Invokes the Linux-based ONNX export script inside the Docker container.
        This takes a PyTorch .ckpt and produces a runnable .onnx and .onnx.json file.
        """
        dojo = self.selected_dojo.get()
        prefix, quality = self.get_dataset_info()
        voice_name = dojo.replace("_dojo", "")
        
        # Determine Epoch for identification
        epoch_match = re.search(r"epoch=(\d+)", ckpt_filename)
        epoch = epoch_match.group(1) if epoch_match else "ckpt"
        
        # Detect "best" checkpoint to apply special naming
        is_best_ckpt = ckpt_filename.startswith("best-") or "_best_" in ckpt_filename
        
        if is_best_ckpt:
            voice_folder = f"{voice_name}_best_{epoch}"
            onnx_filename = f"{prefix}-{voice_name}_{epoch}-best-{quality}.onnx"
        else:
            voice_folder = f"{voice_name}_{epoch}"
            onnx_filename = f"{prefix}-{voice_name}_{epoch}-{quality}.onnx"
        
        # These paths use '../' because the script inside docker is run from the 'scripts/' subfolder
        rel_ckpt = f"../voice_checkpoints/{ckpt_filename}"
        rel_onnx = f"../tts_voices/{voice_folder}/{onnx_filename}"
        
        self.log(f"Exporting model to {onnx_filename} via Docker...", "info")
        
        # Command to run inside the container
        cmd = [
            "docker", "exec", CONTAINER_NAME, "bash", "-c",
            f"cd /app/tts_dojo/{dojo}/scripts && bash utils/_tmux_piper_export.sh {rel_ckpt} {rel_onnx} {dojo}"
        ]
        
        try:
            # We use run() here (not Popen) because we want to wait for completion and get results
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                self.log(f"SUCCESS: Created piper voice model {onnx_filename}", "success")
                self.root.after(0, lambda: self.last_saved_msg.set(f"Last saved: Epoch {epoch}"))
                self.root.after(0, self.find_latest_model) # Refresh tester to offer the new model
            else:
                self.log(f"EXPORT FAILED: {result.stderr}", "error")
        except Exception as e:
            self.log(f"Export execution error: {e}", "error")

    def find_latest_model(self):
        """
        Scans the tts_voices directory for the most recently updated .onnx model.
        Updates the Voice Tester to point to this model if found.
        """
        voices_dir = self.dojo_path / "tts_voices"
        
        # Helper to safely set state when no model is found
        def _no_model_found(msg="No exported voices found yet."):
            self.test_model_msg.set(msg)
            self.speak_btn.config(state="disabled")
            if hasattr(self, "export_prod_btn"):
                self.export_prod_btn.config(state="disabled")

        if not voices_dir.exists():
            return _no_model_found()

        try:
            # Find all .onnx files recursively, ignoring anything in hidden or cache folders
            onnx_files = [p for p in voices_dir.glob("**/*.onnx") if not p.name.startswith('.')]
            if not onnx_files:
                return _no_model_found("No exported voices found in tts_voices.")
                
            # Sort by modification time to find the absolute newest
            newest_onnx = max(onnx_files, key=lambda p: p.stat().st_mtime)
            self.latest_onnx = newest_onnx
            
            # Update UI state on the main thread
            self.root.after(0, lambda: self.test_model_msg.set(f"Ready to test: {newest_onnx.name}"))
            self.root.after(0, lambda: self.speak_btn.config(state="normal"))
            if hasattr(self, "export_prod_btn"):
                self.root.after(0, lambda: self.export_prod_btn.config(state="normal"))
                
        except Exception as e:
            self.log(f"Error scanning for models: {e}", "error")
            _no_model_found("Scan failed (check log)")

    def export_current_model_to_production(self):
        """
        Copies the currently tested .onnx + .onnx.json into the main 'voices/custom' folder.
        This makes the newly trained voice available for the public-facing Piper server.
        """
        if not hasattr(self, "latest_onnx") or not self.latest_onnx:
            messagebox.showwarning("Export", "No exported model found yet.")
            return

        onnx_path: Path = self.latest_onnx
        # Piper requires both the .onnx file and a matching .json configuration file.
        json_path = onnx_path.with_suffix(onnx_path.suffix + ".json")
        if not json_path.exists():
            json_path = onnx_path.with_suffix(".onnx.json")

        if not onnx_path.exists():
            messagebox.showerror("Export", f"Model not found: {onnx_path}")
            return
        if not json_path.exists():
            messagebox.showerror(
                "Export",
                "Missing model config (.onnx.json). Try 'SAVE & EXPORT CURRENT CHECKPOINT' first, then try again.",
            )
            return

        dojo = (self.selected_dojo.get() or "").strip()
        voice_name = dojo.replace("_dojo", "").strip() or "custom"
        # Destination: ../voices/custom/<voice_name>/
        dest_dir = ROOT_DIR / "voices" / "custom" / voice_name
        dest_dir.mkdir(parents=True, exist_ok=True)

        dest_onnx = dest_dir / onnx_path.name
        dest_json = dest_dir / json_path.name

        # --- Handle Overwrites ---
        if dest_onnx.exists() or dest_json.exists():
            overwrite = messagebox.askyesno(
                "Export",
                f"A file already exists in:\n{dest_dir}\n\nOverwrite?",
            )
            if not overwrite:
                return

        try:
            # Perform the copy
            shutil.copy2(onnx_path, dest_onnx)
            shutil.copy2(json_path, dest_json)
        except Exception as e:
            messagebox.showerror("Export", f"Copy failed: {e}")
            return

        # --- Optional config.json update ---
        # Offer to set this as the default voice the server uses on startup.
        set_default = messagebox.askyesno(
            "Export",
            f"Exported to:\n{dest_dir}\n\nSet this voice as the default in src/config.json?",
        )

        if set_default:
            cfg_path = ROOT_DIR / "src" / "config.json"
            cfg = safe_config_load(cfg_path)
            # Update the configuration key
            cfg["voice_model"] = dest_onnx.name
            if safe_config_save(cfg_path, cfg):
                pass
            else:
                messagebox.showwarning(
                    "Export",
                    f"Export succeeded, but failed to update config.json",
                )

        # --- Refresh the running server ---
        # The Piper server caches voices on startup; we try to force a reload.
        refreshed = self._try_refresh_piper_server_cache()
        if refreshed:
            messagebox.showinfo(
                "Export",
                "Export complete and server voice list refreshed.",
            )
        else:
            messagebox.showinfo(
                "Export",
                "Export complete. If the server is running, restart it or wait ~60 seconds for the voice list cache to refresh.",
            )

    def _try_refresh_piper_server_cache(self) -> bool:
        """
        Sends a POST request to the local Piper server's /api/reload-voices endpoint.
        Returns True if the server responded successfully.
        """
        try:
            url = DEFAULT_PIPER_SERVER_URL.rstrip("/") + "/api/reload-voices"
            req = urllib.request.Request(url, method="POST", data=b"{}", headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=2) as resp:
                return 200 <= getattr(resp, "status", 200) < 300
        except Exception:
            return False

    def speak_current_model(self):
        """
        Runs the local 'piper.exe' binary to generate audio from the latest exported model.
        Then plays the resulting WAV file using the Windows Sound API.
        """
        if not hasattr(self, 'latest_onnx') or not self.latest_onnx: return
        
        text = self.test_text.get()
        if not text: return
        
        # Locate the local piper binary
        piper_exe = ROOT_DIR / "src" / "piper" / "piper.exe"
        if not piper_exe.exists():
            self.log("Piper binary not found at " + str(piper_exe), "error")
            return
            
        def work():
            """Background worker for synthesis to avoid hanging the UI thread."""
            self.speak_btn.config(state="disabled")
            self.log(f"Generating audio for: '{text}'...", "info")
            try:
                # Piper writes to this file; then we play it.
                wav_path = ROOT_DIR / "temp_preview.wav"
                
                cmd = [
                    str(piper_exe),
                    "--model", str(self.latest_onnx),
                    "--output_file", str(wav_path)
                ]
                
                # --- Synthesis ---
                # We feed the text to piper's stdin.
                proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                out, err = proc.communicate(input=text.encode('utf-8'))
                
                if proc.returncode != 0:
                    self.log(f"Piper error: {err.decode()}", "error")
                    return
                    
                # --- Playback ---
                if wav_path.exists():
                    self.log("Playing audio...", "info")
                    audio_playback.play_wav_sync(str(wav_path))
                else:
                    self.log("Audio file not created.", "error")
                    
            except Exception as e:
                self.log(f"Speak error: {e}", "error")
            finally:
                self.root.after(0, lambda: self.speak_btn.config(state="normal"))
                
        threading.Thread(target=work, daemon=True).start()

    def get_dataset_info(self):
        """
        Helper to parse the folder prefix and quality from the dojo's config files.
        Used to name exported ONNX models correctly.
        """
        conf_path = self.dojo_path / "target_voice_dataset" / "dataset.conf"
        quality_path = self.dojo_path / "target_voice_dataset" / ".QUALITY"
        
        defaults = _load_global_defaults()
        prefix = (defaults.get("default_piper_filename_prefix") or "en_US").strip()
        quality = "medium"
        
        # Parse the prefix from dataset.conf if it exists
        if conf_path.exists():
            with open(conf_path, 'r', encoding='utf-8') as f:
                content = f.read()
                match = re.search(r'PIPER_FILENAME_PREFIX="([^"]+)"', content)
                if match: prefix = match.group(1)
        
        # Parse the quality from the .QUALITY file if it exists
        if quality_path.exists():
            try:
                q_code = quality_path.read_text().strip()
                if q_code == "L": quality = "low"
                elif q_code == "H": quality = "high"
            except: pass
            
        return prefix, quality

if __name__ == "__main__":
    import argparse

    # Support command-line arguments (e.g. --dojo billy)
    parser = argparse.ArgumentParser()
    parser.add_argument("--dojo", help="Auto-select a dojo (e.g., billy_dojo or billy)")
    args, _unknown = parser.parse_known_args()

    # Standard Tkinter boilerplate
    root = tk.Tk()
    app = TrainingDashboardUI(root)
    
    if args.dojo:
        # Defer selection until the UI event loop starts to ensure combobox and vars are ready.
        root.after(0, lambda: app.select_dojo(args.dojo))
        
    root.mainloop()


