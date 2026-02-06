from __future__ import annotations

import os
import sys
import time
import shutil
import traceback
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Common utilities for sanitization and config management
from common_utils import validate_voice_name, safe_config_save, safe_config_load

# --- Core Modules ---
# Import the downloader module which handles Piper binary acquisition
try:
    import download_piper
except ImportError:
    # Fallback if running from a different context, ensures the local copy is available
    sys.path.append(str(Path(__file__).resolve().parent))
    import download_piper

import audio_playback

# --- Windows Focus Hacks ---
if os.name == 'nt':
    import ctypes
    from ctypes import wintypes

    def force_focus_window(hwnd):
        """
        Forces a window to the foreground on Windows by attaching to the 
        foreground thread input processing (AttachThreadInput hack).
        This bypasses the ASFW (AllowSetForegroundWindow) lock.
        """
        try:
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            
            # Get the current foreground window and its thread
            fg_window = user32.GetForegroundWindow()
            fg_thread_id = user32.GetWindowThreadProcessId(fg_window, None)
            
            # Get our own thread ID
            current_thread_id = kernel32.GetCurrentThreadId()
            
            if fg_window == hwnd:
                return

            if fg_thread_id != current_thread_id:
                # Attach our thread to the foreground thread's input processing
                user32.AttachThreadInput(fg_thread_id, current_thread_id, True)
                
                # Restore if minimized
                if user32.IsIconic(hwnd):
                    user32.ShowWindow(hwnd, 9) # SW_RESTORE
                
                # Force to front
                user32.SetForegroundWindow(hwnd)
                # Backup push
                user32.BringWindowToTop(hwnd)
                
                # Detach
                user32.AttachThreadInput(fg_thread_id, current_thread_id, False)
            else:
                if user32.IsIconic(hwnd):
                    user32.ShowWindow(hwnd, 9)
                user32.SetForegroundWindow(hwnd)
        except Exception as e:
            print(f"Force focus failed: {e}")

# --- File System Paths ---
# Define key paths relative to this script for consistent location across environments
SCRIPT_DIR = Path(__file__).resolve().parent
LOGS_DIR = SCRIPT_DIR.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)
UI_LOG_PATH = LOGS_DIR / "manager.log"

# Setup main logger for the UI with 1MB rotation
ui_logger = logging.getLogger("piper_manager_ui")
ui_logger.setLevel(logging.INFO)
# Prevent duplicate handlers if script is re-imported/re-run in some contexts
if not ui_logger.handlers:
    ui_handler = RotatingFileHandler(UI_LOG_PATH, maxBytes=1024*1024, backupCount=1, encoding="utf-8")
    ui_handler.setFormatter(logging.Formatter("[%(asctime)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    ui_logger.addHandler(ui_handler)

CONFIG_PATH = SCRIPT_DIR / "config.json"
VENV_DIR = SCRIPT_DIR.parent / ".venv"

# --- Environment Detection ---
# Detect OS-specific virtual environment paths (Windows vs Linux/Mac)
if os.name == "nt":
    # Windows-specific paths
    VENV_PYTHON = VENV_DIR / "Scripts" / "python.exe"
    VENV_PYTHONW = VENV_DIR / "Scripts" / "pythonw.exe"
else:
    # Linux/Mac-specific paths (all Unix-like)
    VENV_PYTHON = VENV_DIR / "bin" / "python"
    VENV_PYTHONW = VENV_DIR / "bin" / "python"  # No pythonw on Linux/Mac

# --- Default Configuration ---
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5002
# Registry settings for legacy Windows autostart (cleanup purposes)
RUN_KEY = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE_NAME = "PiperTTS Mockingbird"


def _write_ui_log(msg: str) -> None:
    """Write a message to the UI log file using the rotating logger."""
    try:
        ui_logger.info(msg)
    except Exception:
        # Best-effort logging only.
        pass


def _install_excepthook() -> None:
    """Install a global exception hook to log unhandled exceptions to the UI log."""
    def _hook(exc_type, exc, tb):
        _write_ui_log("UNHANDLED EXCEPTION:\n" + "".join(traceback.format_exception(exc_type, exc, tb)))
        try:
            sys.__excepthook__(exc_type, exc, tb)
        except Exception:
            pass

    sys.excepthook = _hook


_install_excepthook()


# --- Additional Standard Imports ---
import json
import re
import socket
import subprocess
import threading
import queue
import urllib.error
import urllib.request
import webbrowser

# --- GUI Components ---
import tkinter as tk
from tkinter import ttk, filedialog

# Port used to ensure only one instance of the manager is running at a time
SINGLE_INSTANCE_PORT = 5003

def check_single_instance() -> bool:
    """
    Check if another instance is already running using a network socket.
    Returns True if this is the only instance, False otherwise.
    """
    try:
        # Try to bind to the dedicated port on localhost
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(('127.0.0.1', SINGLE_INSTANCE_PORT))
        # Persist the socket reference globally to keep it locked
        globals()['_instance_socket'] = s
        return True
    except socket.error:
        # Port already in use, instance already exists
        return False


def _startup_shortcut_path() -> Path:
    """
    Return the path to the startup shortcut/link for the current OS.
    Currently focuses on the Windows Startup folder.
    """
    if os.name != "nt":
        # Placeholder for non-Windows platforms
        return SCRIPT_DIR / "autostart_dummy"
        
    appdata = os.environ.get("APPDATA")
    if not appdata:
        # Emergency fallback for odd Windows configurations
        return SCRIPT_DIR / "PiperTTS Mockingbird.lnk"
    
    # Path to the User's Startup folder in the Start Menu
    return (
        Path(appdata)
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs"
        / "Startup"
        / "PiperTTS Mockingbird.lnk"
    )


def _ps_single_quote(value: str) -> str:
    """Escape a string for use in a PowerShell single-quoted string."""
    return "'" + value.replace("'", "''") + "'"


def _now() -> str:
    """Return the current time as a string."""
    return time.strftime("%H:%M:%S")


def log_to(widget: tk.Text, msg: str, save_to_file: bool = True) -> None:
    """
    Append a message to a Tkinter Text widget and optionally save to log file.
    This function is thread-safe.
    """
    if save_to_file:
        _write_ui_log(msg)

    def _execute():
        try:
            if not widget.winfo_exists():
                return
            widget.configure(state="normal")
            widget.insert("end", f"[{_now()}] {msg}\n")
            widget.see("end")
            widget.configure(state="disabled")
        except Exception:
            pass

    try:
        widget.after(0, _execute)
    except Exception:
        # Fallback if widget is already destroyed
        pass


def run_cmd_capture(args: list[str], cwd: Path | None = None) -> tuple[int, str]:
    """
    Run a command and capture its output (merged stdout/stderr).
    Suppresses the console window pop-up on Windows systems.
    """
    try:
        kwargs = {}
        if os.name == "nt":
            # 0x08000000 = CREATE_NO_WINDOW: Ensures no terminal window flashes open
            kwargs["creationflags"] = 0x08000000

        p = subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            shell=False,
            **kwargs,
        )
        return p.returncode, (p.stdout or "").strip()
    except Exception as e:
        return 1, str(e)


def run_cmd_realtime(args: list[str], log_widget: tk.Text, progress_callback=None, cwd: Path | None = None) -> int:
    """
    Execute a process and stream its output live to a Tkinter Text widget.
    Also parses 'PROGRESS:' messages to trigger UI progress bar updates.
    """
    try:
        kwargs = {}
        if os.name == "nt":
            kwargs["creationflags"] = 0x08000000 # CREATE_NO_WINDOW

        p = subprocess.Popen(
            args,
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            shell=False,
            bufsize=1, # Line buffering for interactive feedback
            **kwargs,
        )

        full_output = []
        if p.stdout:
            # Read output stream line by line
            for line in iter(p.stdout.readline, ""):
                line_str = line.strip()
                # Intercept progress markers for the UI bar
                if line_str.startswith("PROGRESS:"):
                    try:
                        # Protocol: PROGRESS:current/total
                        parts = line_str.replace("PROGRESS:", "").split("/")
                        if len(parts) == 2:
                            current = int(parts[0])
                            total = int(parts[1])
                            percent = (current / total) * 100
                            if progress_callback:
                                progress_callback(percent, f"{current}/{total}")
                    except Exception:
                        pass
                else:
                    # Echo standard output to the manager's log window
                    log_to(log_widget, line_str, save_to_file=False)
                full_output.append(line)
        
        p.stdout.close()
        return_code = p.wait()
        return return_code
    except Exception as e:
        log_to(log_widget, f"Error executing realtime command: {e}")
        return 1


def ensure_venv_and_deps(log: tk.Text) -> bool:
    """
    Self-healing setup: ensures the .venv exists, is compatible (Python < 3.13),
    and has all required packages installed.
    """
    # Audio-related libraries (pydub) are currently incompatible with Python 3.13 due to 'audioop' removal.
    if VENV_PYTHON.exists():
        try:
            code, out = run_cmd_capture([str(VENV_PYTHON), "--version"])
            if " 3.13" in out or " 3.14" in out:
                log_to(log, "Incompatible environment (Python 3.13+ detected). Re-initializing with 3.10...")
                shutil.rmtree(VENV_DIR, ignore_errors=True)
        except Exception:
            pass

    # Create the virtual environment if missing or purged above
    if not VENV_PYTHON.exists():
        log_to(log, f"Scaffolding virtual environment: {VENV_DIR}")
        
        # Search for a compatible local Python installation (< 3.13) to use as base
        python_exe = sys.executable
        # List common Windows install paths for older versions to ensure pydub/audioop compatibility
        compatible_versions = ["3.12", "3.11", "3.10", "3.9"]
        found_compatible = False
        
        # 1. Try 'py' launcher with specific versions
        if os.name == 'nt':
            for ver in compatible_versions:
                try:
                    code, out = run_cmd_capture(["py", f"-{ver}", "-c", "import sys; print(sys.executable)"])
                    if code == 0 and out.strip():
                        python_exe = out.strip()
                        log_to(log, f"Found compatible Python {ver} via launcher: {python_exe}")
                        found_compatible = True
                        break
                except Exception:
                    continue
        
        # 2. Try hardcoded paths if launcher failed
        if not found_compatible:
            local_appdata = os.environ.get("LOCALAPPDATA", "")
            possible_paths = []
            for ver in ["312", "311", "310", "39"]:
                possible_paths.append(Path(local_appdata) / "Programs" / "Python" / f"Python{ver}" / "python.exe")
                possible_paths.append(Path(f"C:/Program Files/Python{ver}/python.exe"))
                possible_paths.append(Path(f"C:/Python{ver}/python.exe"))

            for p in possible_paths:
                if p.exists():
                    python_exe = str(p)
                    log_to(log, f"Found compatible Python at: {python_exe}")
                    found_compatible = True
                    break
        
        if not found_compatible and (" 3.13" in sys.version or " 3.14" in sys.version):
            log_to(log, "WARNING: No Python 3.9-3.12 found. Attempting with current version, but pydub may fail.")

        code, out = run_cmd_capture([python_exe, "-m", "venv", str(VENV_DIR)], cwd=SCRIPT_DIR)
        if code != 0:
            log_to(log, f"Critical Failure: Could not create venv (code {code}):\n{out}")
            return False

    # Validation: ensure a requirements file exists
    req = SCRIPT_DIR / "requirements.txt"
    if not req.exists():
        log_to(log, "requirements.txt missing; creating basic defaults.")
        req.write_text("fastapi\nuvicorn\npydantic\n", encoding="utf-8")

    # Optimization: Verify if major dependencies are already active to skip pip lag
    code, _ = run_cmd_capture([str(VENV_PYTHON), "-c", "import fastapi; import uvicorn; import pydub; import numpy"], cwd=SCRIPT_DIR)
    if code == 0:
        return True

    log_to(log, "Installing/Updating library dependencies (pip)...")
    # Upgrade pip to handle modern packages correctly
    code, out = run_cmd_capture([str(VENV_PYTHON), "-m", "pip", "install", "--upgrade", "pip"], cwd=SCRIPT_DIR)
    if code != 0:
        log_to(log, f"pip maintenance failed (code {code}):\n{out}")
        return False

    # Install the full stack from requirements.txt
    code, out = run_cmd_capture([str(VENV_PYTHON), "-m", "pip", "install", "-r", str(req)], cwd=SCRIPT_DIR)
    if code != 0:
        log_to(log, f"Critical Failure: pip installation failed (code {code}):\n{out}")
        return False

    return True


# --- Initial Voice Model Stack ---
STARTER_MODELS = {
    "Ryan (High)": {
        "onnx_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/high/en_US-ryan-high.onnx?download=true",
        "json_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/high/en_US-ryan-high.onnx.json?download=true",
        "rel_path": "voices/Ryan/en_US-ryan-high.onnx"
    },
    "Cori (High)": {
        "onnx_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/cori/high/en_GB-cori-high.onnx?download=true",
        "json_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/cori/high/en_GB-cori-high.onnx.json?download=true",
        "rel_path": "voices/Cori/en_GB-cori-high.onnx"
    },
    "Female (Medium)": {
        "onnx_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/hfc_female/medium/en_US-hfc_female-medium.onnx?download=true",
        "json_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/hfc_female/medium/en_US-hfc_female-medium.onnx.json?download=true",
        "rel_path": "voices/female/en_US-hfc_female-medium.onnx"
    },
    "Male (Medium)": {
        "onnx_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/hfc_male/medium/en_US-hfc_male-medium.onnx?download=true",
        "json_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/hfc_male/medium/en_US-hfc_male-medium.onnx.json?download=true",
        "rel_path": "voices/male/en_US-hfc_male-medium.onnx"
    }
}

def ensure_starter_models(log: tk.Text) -> bool:
    """
    Checks for the minimum set of voice models and downloads them from Hugging Face if missing.
    Ensures both the .onnx model and the .onnx.json configuration are present.
    """
    voices_root = SCRIPT_DIR.parent
    
    all_good = True
    
    for name, info in STARTER_MODELS.items():
        onnx_path = voices_root / info["rel_path"]
        json_path = onnx_path.with_suffix(".onnx.json")
        
        # Structure the voices/ sub-folder (e.g., voices/Ryan/)
        onnx_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Validate/Download the primary ONNX binary
        if not onnx_path.exists():
            log_to(log, f"Model Missing: Initializing download for {name}...")
            try:
                log_to(log, f"  Fetching from: {info['onnx_url']}...")
                
                # Atomic-like download: fetch to a .tmp file first to prevent half-finished garbage
                temp_path = onnx_path.with_suffix(".tmp")
                urllib.request.urlretrieve(info["onnx_url"], temp_path)
                
                # Commit the download by renaming on success
                if temp_path.exists():
                    temp_path.replace(onnx_path)
                    log_to(log, f"  Deployment successful: {onnx_path.name}")
                else:
                    log_to(log, f"  Critical Error: Temporary file disappeared during download for {name}")
                    all_good = False
                    
            except Exception as e:
                log_to(log, f"Failed to acquire {name}: {e}")
                all_good = False
                continue

        # Validate/Download the metadata JSON
        if not json_path.exists():
            try:
                # Small config file, fetch and move
                temp_json = json_path.with_suffix(".tmp")
                urllib.request.urlretrieve(info["json_url"], temp_json)
                
                if temp_json.exists():
                    temp_json.replace(json_path)
                    log_to(log, f"  Configuration loaded for {name}")
            except Exception as e:
                log_to(log, f"Failed to acquire config for {name}: {e}")
                all_good = False
    
    if all_good:
        log_to(log, "Default voice model state verified.")
    
    return all_good


def ensure_piper_binary(log: tk.Text) -> bool:
    """
    Checks for the Piper C++ executable in the expected src/piper/ location.
    If not found, it triggers a remote fetch and local extraction.
    """
    piper_dir = SCRIPT_DIR / "piper"
    
    # OS target file naming
    exe_name = "piper.exe" if os.name == "nt" else "piper"
    
    # Search in default and nested directory patterns
    if (piper_dir / exe_name).exists():
        return True
    if (piper_dir / "piper" / exe_name).exists():
        return True

    log_to(log, "Core binary 'piper' not found. Launching downloader...")
    
    # Capture the downloader's terminal output and pipe it into the UI log
    class LogRedirect:
        def __init__(self, text_widget):
            self.text_widget = text_widget
        def write(self, msg):
            if msg.strip():
                # Relay to UI thread safely via after()
                self.text_widget.after(0, lambda: log_to(self.text_widget, msg.strip()))
        def flush(self):
            pass

    original_stdout = sys.stdout
    try:
        sys.stdout = LogRedirect(log)
        # Execute the automated download and extraction logic
        download_piper.download_and_extract_piper(SCRIPT_DIR)
    except Exception as e:
        log_to(log, f"Binary deployment failure: {e}")
        return False
    finally:
        sys.stdout = original_stdout

    # Final check of disk state
    if (piper_dir / exe_name).exists() or (piper_dir / "piper" / exe_name).exists():
        log_to(log, "Piper engine deployed successfully.")
        return True
    
    log_to(log, "Binary installation completed but executable is not in the expected path.")
    return False


def http_get_json(url: str, timeout: float = 5.0) -> dict:
    """Perform an HTTP GET request and return the JSON response."""
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    return json.loads(data.decode("utf-8"))


def http_post_json(url: str, payload: dict, timeout: float = 10.0) -> bytes:
    """Perform an HTTP POST request with a JSON payload and return the response bytes."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        method="POST",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def powershell(args: str) -> tuple[int, str]:
    """Run a PowerShell command and return its exit code and output."""
    return run_cmd_capture(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", args], cwd=SCRIPT_DIR)


def stop_server_by_port(log: tk.Text, port: int) -> bool:
    """
    Finds and terminates any process currently bound to the specified TCP port.
    Crucial for clearing 'ghost' processes before starting a new server instance.
    """
    if os.name != "nt":
        # Unix-like (Mac/Linux) port cleanup using the 'lsof' utility
        if not shutil.which("lsof"):
            log_to(log, "System Error: 'lsof' not found. Automatic port reclamation disabled.")
            return False

        try:
            # -t: terse output (PID only), -i: Internet socket matching the port
            cmd = ["lsof", "-t", "-i", f":{port}"]
            code, out = run_cmd_capture(cmd)
            if code != 0 or not out.strip():
                log_to(log, f"No active listener detected on port {port}.")
                return True
            
            pids = out.strip().split()
            for pid in pids:
                # Force kill (SIGKILL) to ensure the port is immediately available
                run_cmd_capture(["kill", "-9", pid])
            
            log_to(log, f"Successfully reclaimed port {port} (Terminated PIDs: {', '.join(pids)}).")
            return True
        except Exception as e:
            log_to(log, f"Platform Port Reclamation failed: {e}")
            return False

    # Windows-native port cleanup using PowerShell
    ps = (
        f"$p={port}; "
        f"$procs = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue | "
        f"Select-Object -ExpandProperty OwningProcess -Unique; "
        f"if (-not $procs) {{ Write-Output 'NO_LISTENER'; exit 0 }}; "
        f"foreach ($processId in $procs) {{ Stop-Process -Id $processId -Force }}; "
        f"Write-Output 'STOPPED'"
    )
    code, out = powershell(ps)
    if code != 0:
        log_to(log, f"Windows Port Reclamation failed (code {code}):\n{out}")
        return False
    if out.strip() == "NO_LISTENER":
        log_to(log, f"No active listener detected on port {port}.")
        return True
    log_to(log, f"Port {port} reclaimed by PowerShell.")
    return True


def start_server_process(log: tk.Text, host: str, port: int) -> bool:
    """
    Initializes the Piper TTS Server (FastAPI/Uvicorn) as a background process.
    Performs prerequisite checks before launching.
    """
    if not ensure_venv_and_deps(log):
        return False
    
    # Validation chain: Binary -> Models
    if not ensure_piper_binary(log):
        log_to(log, "Startup Aborted: Piper executable missing.")
        return False

    if not ensure_starter_models(log):
        log_to(log, "Startup Warning: Some voice models could not be verified.")

    # Select the appropriate Python interpreter for background execution
    python_for_server = VENV_PYTHON
    if os.name == "nt" and VENV_PYTHONW.exists():
        # Use pythonw (no-window) on Windows for a cleaner background experience
        python_for_server = VENV_PYTHONW

    # Command construction for Uvicorn
    cmd = [
        str(python_for_server),
        "-m",
        "uvicorn",
        "piper_server:app",
        "--host",
        host,
        "--port",
        str(port),
    ]

    log_to(log, f"Initializing Server Instance: {' '.join(cmd)}")

    # Launch as a fully detached process group
    kwargs = {}
    if os.name == "nt":
        # Disconnect from parent console and hide window
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "CREATE_NO_WINDOW", 0)

    # Capture startup errors to help diagnose failures
    server_log_path = SCRIPT_DIR / "piper_server.log"
    try:
        # Open log file in append mode to capture both normal logs and startup errors
        log_file = open(server_log_path, "a", encoding="utf-8")
        log_file.write(f"\n{'='*60}\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Server startup initiated\n{'='*60}\n")
        log_file.flush()
        
        subprocess.Popen(
            cmd,
            cwd=str(SCRIPT_DIR),
            stdout=log_file,
            stderr=subprocess.STDOUT,  # Merge stderr into stdout for unified logging
            **kwargs,
        )
        # Don't close the file handle - let the subprocess inherit it
    except Exception as e:
        log_to(log, f"Process Initiation Failed: {e}")
        try:
            log_file.close()
        except:
            pass
        return False

    return True


def autostart_install(log: tk.Text) -> bool:
    """
    Registers the server manager to launch on system startup.
    Delegates to platform-specific installers.
    """
    if os.name == "nt":
        return _autostart_install_windows(log)
    elif sys.platform == "darwin":
        return _autostart_install_mac(log)
    else:
        return _autostart_install_linux(log)

def _autostart_install_windows(log: tk.Text) -> bool:
    """Creates a shortcut in the User's Startup folder (.lnk via PowerShell)."""
    bat = SCRIPT_DIR / "tools" / "start_piper_server.bat"
    if not bat.exists():
        log_to(log, "Installation Error: Missing start_piper_server.bat helper.")
        return False

    link_path = _startup_shortcut_path()
    link_path.parent.mkdir(parents=True, exist_ok=True)

    # Use a COM object via PowerShell to generate a Windows Link (.lnk)
    ps = (
        f"$WshShell = New-Object -ComObject WScript.Shell; "
        f"$Shortcut = $WshShell.CreateShortcut({_ps_single_quote(str(link_path))}); "
        f"$Shortcut.TargetPath = {_ps_single_quote(str(bat))}; "
        f"$Shortcut.WorkingDirectory = {_ps_single_quote(str(SCRIPT_DIR))}; "
        f"$Shortcut.WindowStyle = 7; " # 7 = Starts Minimized
        f"$Shortcut.Save(); "
        f"Write-Output 'OK'"
    )

    code, out = powershell(ps)
    if code != 0:
        log_to(log, f"Shortcut Creation Failed (code {code}):\n{out}")
        return False

    if not link_path.exists():
        log_to(log, "Validation Error: Shortcut file was not committed to disk.")
        return False

    # Migration: Purge old Registry-based autostart if it exists
    run_cmd_capture(["reg", "delete", RUN_KEY, "/v", RUN_VALUE_NAME, "/f"], cwd=SCRIPT_DIR)

    log_to(log, "Autostart configured via Startup Folder Shortcut.")
    return True

def _autostart_install_mac(log: tk.Text) -> bool:
    """Install autostart on macOS using a LaunchAgent plist file."""
    plist_path = Path.home() / "Library" / "LaunchAgents" / "com.piper.tts.plist"
    start_script = SCRIPT_DIR.parent / "start.sh"
    
    if not start_script.exists():
        log_to(log, "Missing start.sh in parent directory.")
        return False
        
    # Ensure start.sh is executable
    try:
        start_script.chmod(start_script.stat().st_mode | 0o111)
    except Exception as e:
        log_to(log, f"Warning: Could not chmod start.sh: {e}")

    # Define the plist content for the LaunchAgent
    plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.piper.tts</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>{start_script}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/piper_tts.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/piper_tts.err</string>
</dict>
</plist>
"""
    try:
        plist_path.parent.mkdir(parents=True, exist_ok=True)
        plist_path.write_text(plist_content, encoding="utf-8")
        
        # Load the LaunchAgent immediately
        run_cmd_capture(["launchctl", "load", str(plist_path)])
        
        log_to(log, f"Enabled autostart (LaunchAgent created at {plist_path}).")
        return True
    except Exception as e:
        log_to(log, f"Autostart install failed: {e}")
        return False

def _autostart_install_linux(log: tk.Text) -> bool:
    """Install autostart on Linux using an XDG Desktop Entry."""
    desktop_path = Path.home() / ".config" / "autostart" / "piper-tts.desktop"
    start_script = SCRIPT_DIR.parent / "start.sh"
    
    if not start_script.exists():
        log_to(log, "Missing start.sh in parent directory.")
        return False

    # Ensure start.sh is executable
    try:
        start_script.chmod(start_script.stat().st_mode | 0o111)
    except Exception as e:
        log_to(log, f"Warning: Could not chmod start.sh: {e}")

    # Define the desktop entry content
    content = f"""[Desktop Entry]
Type=Application
Name=Piper TTS Server
Comment=Start Piper TTS Server
Exec=/bin/bash "{start_script}"
Path={SCRIPT_DIR}
Terminal=false
Hidden=false
X-GNOME-Autostart-enabled=true
"""
    try:
        desktop_path.parent.mkdir(parents=True, exist_ok=True)
        desktop_path.write_text(content, encoding="utf-8")
        log_to(log, f"Enabled autostart (XDG Desktop entry created at {desktop_path}).")
        return True
    except Exception as e:
        log_to(log, f"Autostart install failed: {e}")
        return False


def autostart_uninstall(log: tk.Text) -> bool:
    """Remove the autostart mechanism for the current OS."""
    if os.name == "nt":
        return _autostart_uninstall_windows(log)
    elif sys.platform == "darwin":
        return _autostart_uninstall_mac(log)
    else:
        return _autostart_uninstall_linux(log)

def _autostart_uninstall_windows(log: tk.Text) -> bool:
    """Remove the Windows startup shortcut."""
    link_path = _startup_shortcut_path()
    try:
        link_path.unlink()
        log_to(log, "Disabled autostart (Startup folder shortcut removed).")
    except FileNotFoundError:
        log_to(log, "Autostart shortcut not found (already disabled).")
    except Exception as e:
        log_to(log, f"Autostart uninstall failed: {e}")
        return False

    # Cleanup legacy Run-key entry (older versions used this); ignore failures.
    run_cmd_capture(["reg", "delete", RUN_KEY, "/v", RUN_VALUE_NAME, "/f"], cwd=SCRIPT_DIR)
    return True

def _autostart_uninstall_mac(log: tk.Text) -> bool:
    """Remove the macOS LaunchAgent plist."""
    plist_path = Path.home() / "Library" / "LaunchAgents" / "com.piper.tts.plist"
    try:
        if plist_path.exists():
            run_cmd_capture(["launchctl", "unload", str(plist_path)])
            plist_path.unlink()
            log_to(log, "Disabled autostart (LaunchAgent removed).")
        else:
            log_to(log, "Autostart not found (already disabled).")
        return True
    except Exception as e:
        log_to(log, f"Autostart uninstall failed: {e}")
        return False

def _autostart_uninstall_linux(log: tk.Text) -> bool:
    """Remove the Linux XDG Desktop entry."""
    desktop_path = Path.home() / ".config" / "autostart" / "piper-tts.desktop"
    try:
        if desktop_path.exists():
            desktop_path.unlink()
            log_to(log, "Disabled autostart (Desktop entry removed).")
        else:
            log_to(log, "Autostart not found (already disabled).")
        return True
    except Exception as e:
        log_to(log, f"Autostart uninstall failed: {e}")
        return False


def autostart_query() -> tuple[bool, str]:
    """Check if autostart is currently enabled and return a status label."""
    if os.name == "nt":
        shortcut_installed = _startup_shortcut_path().exists()
        legacy_installed = run_cmd_capture(["reg", "query", RUN_KEY, "/v", RUN_VALUE_NAME], cwd=SCRIPT_DIR)[0] == 0

        if shortcut_installed and legacy_installed:
            return True, "Enabled (shortcut + legacy)"
        if shortcut_installed:
            return True, "Enabled (Startup shortcut)"
        if legacy_installed:
            return True, "Enabled (Legacy Run key)"
        return False, "Disabled"
    
    elif sys.platform == "darwin":
        plist_path = Path.home() / "Library" / "LaunchAgents" / "com.piper.tts.plist"
        if plist_path.exists():
            return True, "Enabled (LaunchAgent)"
        return False, "Disabled"
        
    else:
        # Linux
        desktop_path = Path.home() / ".config" / "autostart" / "piper-tts.desktop"
        if desktop_path.exists():
            return True, "Enabled (XDG Autostart)"
        return False, "Disabled"


def scan_voices() -> list[Path]:
    """Scan voices/ folder for all .onnx files."""
    voices_dir = SCRIPT_DIR.parent / "voices"
    if not voices_dir.exists():
        return []
    return sorted(voices_dir.rglob("*.onnx"))


def load_config() -> dict:
    """Load config.json with backup recovery."""
    return safe_config_load(CONFIG_PATH)


def save_config(cfg: dict) -> None:
    """Save config to config.json with backup and atomic write."""
    safe_config_save(CONFIG_PATH, cfg)


class App(ttk.Frame):
    """
    Main Application UI Class.
    Encapsulates the entire Manager interface, logic, and background monitoring.
    """
    def __init__(self, master: tk.Tk):
        super().__init__(master)
        self.master = master

        # --- UI Binding Variables ---
        self.host_var = tk.StringVar(value=DEFAULT_HOST)
        self.port_var = tk.IntVar(value=DEFAULT_PORT)
        self.voice_var = tk.StringVar()
        self.random_var = tk.BooleanVar(value=True) # If true, use canned test phrases
        self.auto_restart_var = tk.BooleanVar(value=False)
        self.launch_on_startup_var = tk.BooleanVar(value=False)
        self.desktop_shortcut_var = tk.BooleanVar(value=False)
        self.show_training_var = tk.BooleanVar(value=False) # Collapsible training section

        self.status_var = tk.StringVar(value="â— UNKNOWN")
        self.autostart_var = tk.StringVar(value="Autostart: unknown")

        # --- Functional State Trackers ---
        self.is_playing = False          # True when local audio playback is active
        self.playback_process = None     # Handle for external player processes (Mac/Linux)
        self._loading_active = False     # Toggle for the 'Generating...' UI animation
        self._should_be_running = False  # Track user intent (Start vs Stop) for auto-restart
        self._last_restart_time = 0      # Throttling to prevent restart loops
        self.transition_state = None     # None, 'STARTING', 'STOPPING' - prevents double-clicks

        # Initialize environment data
        self.available_voices = scan_voices()
        self._load_settings()

        # UI Badge Color Styles
        self._status_style = "Badge.Unknown.TLabel"
        self._autostart_style = "Badge.Unknown.TLabel"

        # Construct the layout
        self._build()
        self._refresh_autostart()
        
        # Start periodic status updates (every 5s)
        self._schedule_status_refresh()

        # --- Background Task Initiation ---
        # 1. Verify filesystem state (Piper binary, models)
        self._thread(self._initial_setup_check)
        
        # 2. Pipe server-side logs into the UI window
        self._thread(self._monitor_server_log)

    def _monitor_server_log(self) -> None:
        """
        Background Thread: Tails 'piper_server.log' and displays updates in the UI.
        Enables visibility into server-side events without opening log files manually.
        """
        server_log = SCRIPT_DIR / "piper_server.log"
        
        # Spin until the server process actually creates the log file
        while True:
            if server_log.exists():
                break
            if not self.master.winfo_exists():
                return
            time.sleep(2)
            
        try:
            with open(server_log, "r", encoding="utf-8") as f:
                # Start reading from the current end of the file
                f.seek(0, 2)
                while True:
                    if not self.master.winfo_exists():
                        # Stop trailing if the UI window is closed
                        break
                    line = f.readline()
                    if line:
                        msg = line.strip()
                        if msg:
                            # Update UI from thread: use after() and disable recursive disk logging
                            self.master.after(0, lambda m=msg: log_to(self.log, f"[SERVER] {m}", save_to_file=False))
                    else:
                        time.sleep(0.5) # Efficiency pause
        except Exception:
            pass

    def _initial_setup_check(self) -> None:
        """
        One-time Background Check: Ensures the user has the necessary local files
        (Piper binary + Starter Models) at application launch.
        """
        # Ensure engine is present
        ensure_piper_binary(self.log)
        
        # Ensure default voices are present
        if ensure_starter_models(self.log):
            # If models were newly added, refresh the dropdown menu
            self.master.after(0, self._refresh_voices)

    def _refresh_voices(self) -> None:
        """
        Synchronizes the Voice Selection dropdown with the current state of the 'voices/' folder.
        """
        self.available_voices = scan_voices()
        if hasattr(self, "voice_combo"):
            self.voice_combo["values"] = [v.name for v in self.available_voices]
            
            # Select first available voice if current choice is invalid/missing
            current = self.voice_var.get()
            if not current or not any(v.name == current for v in self.available_voices):
                if self.available_voices:
                    self.voice_var.set(self.available_voices[0].name)
        
        log_to(self.log, f"Scanner update: Local voice library contains {len(self.available_voices)} model(s).")

    def _build(self) -> None:
        self.master.title("PiperTTS Mockingbird • Manager Dashboard")
        
        # Force window to front on startup using robust ASFW bypass
        try:
            self.master.lift()
            self.master.attributes("-topmost", True)
            self.master.update()
            
            # Apply the Ctypes hack if on Windows
            if os.name == 'nt':
                # Get the OS window handle (HWND) for the root Tk window
                # winfo_id() returns the window ID, but we usually need the parent for the main frame
                hwnd = ctypes.windll.user32.GetParent(self.master.winfo_id())
                if hwnd:
                    force_focus_window(hwnd)
                else:
                    # Fallback if GetParent fails (sometimes happens with certain Tk versions)
                    force_focus_window(self.master.winfo_id())

            self.master.focus_force()
            self.master.after(200, lambda: [
                self.master.attributes("-topmost", False),
                self.master.focus_set()
            ])
        except Exception as e:
            print(f"Focus error: {e}")
            pass

        self.grid(row=0, column=0, sticky="nsew")
        self.master.columnconfigure(0, weight=1)
        self.master.rowconfigure(0, weight=1)

        # Set modern color scheme
        self.master.configure(bg="#f8fafc")
        self.configure(style="Modern.TFrame")

        style = ttk.Style()
        # Use native theme on Windows for better-looking checkboxes
        if os.name == "nt":
            available_themes = style.theme_names()
            if "vista" in available_themes:
                style.theme_use("vista")
            elif "xpnative" in available_themes:
                style.theme_use("xpnative")
            else:
                style.theme_use("clam")
        else:
            try:
                style.theme_use("clam")
            except Exception:
                pass

        # Modern color palette
        style.configure("Modern.TFrame", background="#f8fafc")
        style.configure("Card.TLabelframe", background="#ffffff", borderwidth=1, relief="solid")
        style.configure("Card.TLabelframe.Label", background="#ffffff", foreground="#1e293b", font=("Segoe UI", 11, "bold"))

        # Use a canvas for the scrollable part (all but the log)
        scroll_container = ttk.Frame(self, style="Modern.TFrame")
        scroll_container.grid(row=0, column=0, sticky="nsew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        canvas = tk.Canvas(scroll_container, highlightthickness=0, bg="#f8fafc")
        v_scrollbar = ttk.Scrollbar(scroll_container, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas, style="Modern.TFrame")

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        
        def _on_canvas_configure(event):
            canvas.itemconfig(1, width=event.width)
        canvas.bind("<Configure>", _on_canvas_configure)

        canvas.configure(yscrollcommand=v_scrollbar.set)

        # Enable mouse wheel scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        
        def _bind_mousewheel(event):
            canvas.bind_all("<MouseWheel>", _on_mousewheel)
        
        def _unbind_mousewheel(event):
            canvas.unbind_all("<MouseWheel>")
        
        # Bind when mouse enters the canvas area
        canvas.bind("<Enter>", _bind_mousewheel)
        canvas.bind("<Leave>", _unbind_mousewheel)

        v_scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        # Modern badge styles with better colors and sizing
        style.configure("Badge.Running.TLabel", foreground="#10b981", background="#f8fafc", font=("Segoe UI", 13, "bold"))
        style.configure("Badge.Stopped.TLabel", foreground="#ef4444", background="#f8fafc", font=("Segoe UI", 13, "bold"))
        style.configure("Badge.Error.TLabel", foreground="#f59e0b", background="#f8fafc", font=("Segoe UI", 13, "bold"))
        style.configure("Badge.Unknown.TLabel", foreground="#94a3b8", background="#f8fafc", font=("Segoe UI", 13, "bold"))
        
        # Modern button styles
        style.configure("Accent.TButton", font=("Segoe UI", 10), padding=8)
        style.configure("TButton", font=("Segoe UI", 9), padding=6)

        # --- Re-parenting all sections into scrollable_frame ---

        # Server section (FIRST - like SearXNG)
        top = ttk.LabelFrame(scrollable_frame, text="🚀 Server Control", style="Card.TLabelframe")
        top.pack(fill="x", padx=15, pady=(15, 12))
        top.columnconfigure(0, weight=1)
        top.configure(padding=10)

        # Status display
        status_container = ttk.Frame(top, style="Modern.TFrame")
        status_container.grid(row=0, column=0, sticky="w", padx=12, pady=(12, 12))
        
        self.status_label = ttk.Label(status_container, textvariable=self.status_var, style=self._status_style)
        self.status_label.pack(anchor="w")

        # Control buttons
        btns = ttk.Frame(top, style="Modern.TFrame")
        btns.grid(row=1, column=0, sticky="w", padx=12, pady=(0, 16))

        ttk.Button(btns, text="▶ Start Server", command=self._start_clicked, width=18, style="Accent.TButton").grid(row=0, column=0, padx=(0, 6))
        ttk.Button(btns, text="⏹ Stop Server", command=self._stop_clicked, width=18).grid(row=0, column=1, padx=6)
        ttk.Button(btns, text="🔄 Check Status", command=self._status_clicked, width=18).grid(row=0, column=2, padx=6)

        # Separator line
        ttk.Separator(top, orient="horizontal").grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 12))

        # Checkboxes
        checks_frame = ttk.Frame(top, style="Modern.TFrame")
        checks_frame.grid(row=4, column=0, sticky="w", padx=12, pady=(0, 12))
        
        ttk.Checkbutton(checks_frame, text="Launch server automatically on Windows startup", variable=self.launch_on_startup_var, command=self._save_settings, style="TCheckbutton").pack(anchor="w", pady=3)
        ttk.Label(
            checks_frame, 
            text="💡 Tip: PiperTTS Mockingbird needs this server to work. If this is not checked, you'll have to\nmanually start the server every time you restart your computer.", 
            font=("Segoe UI", 8),
            foreground="#64748b",
            background="#f8fafc",
            justify=tk.LEFT
        ).pack(anchor="w", padx=24, pady=(2, 8))
        
        ttk.Checkbutton(checks_frame, text="Auto-Restart server if it crashes", variable=self.auto_restart_var, command=self._save_settings, style="TCheckbutton").pack(anchor="w", pady=(8, 0))

        # Separator before recommendation
        ttk.Separator(top, orient="horizontal").grid(row=5, column=0, sticky="ew", padx=12, pady=(8, 12))

        # Web UI Recommendation
        webui_rec_frame = ttk.Frame(top, style="Modern.TFrame")
        webui_rec_frame.grid(row=6, column=0, sticky="w", padx=12, pady=(0, 12))
        
        ttk.Label(
            webui_rec_frame, 
            text="The Open Web UI interface offers more features and a better user experience than this manager.", 
            font=("Segoe UI", 9),
            foreground="#0f172a",
            background="#f8fafc",
            justify=tk.LEFT
        ).pack(anchor="w", pady=(0, 8))
        
        ttk.Button(webui_rec_frame, text="🌐 Open Web UI (Recommended)", command=self._open_web_dashboard, style="Accent.TButton", width=30).pack(anchor="w")

        # Server Configuration section (consolidated connectivity)
        conn = ttk.LabelFrame(scrollable_frame, text="🔌 Server Configuration", style="Card.TLabelframe")
        conn.pack(fill="x", padx=15, pady=(0, 12))
        conn.columnconfigure(0, weight=1)
        conn.configure(padding=10)

        # Server configuration
        config_frame = ttk.Frame(conn, style="Modern.TFrame")
        config_frame.pack(anchor="w", padx=12, pady=(12, 8))
        
        ttk.Label(config_frame, text="Host:", font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Entry(config_frame, textvariable=self.host_var, width=18).grid(row=0, column=1, sticky="w", padx=(0, 20))

        ttk.Label(config_frame, text="Port:", font=("Segoe UI", 9)).grid(row=0, column=2, sticky="w", padx=(0, 6))
        ttk.Entry(config_frame, textvariable=self.port_var, width=8).grid(row=0, column=3, sticky="w")

        ttk.Label(conn, text="If an app uses PiperTTS Mockingbird, it will want you to paste this URL somewhere:",
                 font=("Segoe UI", 9), background="#f8fafc").pack(anchor="w", padx=12, pady=(8, 8))
        
        url_frame = ttk.Frame(conn, style="Modern.TFrame")
        url_frame.pack(fill="x", padx=12, pady=(0, 12))
        url_frame.columnconfigure(0, weight=1)

        self.url_entry = ttk.Entry(url_frame, font=("Consolas", 10), state="readonly")
        self.url_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        
        self.copy_url_btn = ttk.Button(url_frame, text="📋 Copy URL", width=12, command=self.copy_url)
        self.copy_url_btn.grid(row=0, column=1, padx=(0, 8))
        
        ttk.Button(url_frame, text="🌐 Open Web UI", width=14, command=self._open_web_dashboard, style="Accent.TButton").grid(row=0, column=2)
        
        # Initialize URL display
        self.update_url_display()
        
        ttk.Label(conn, text="💡 Tip: Once the browser page is open, create a bookmark for quick access.", 
                 font=("Segoe UI", 8), foreground="#d97706", background="#f8fafc", justify=tk.LEFT).pack(anchor="w", padx=12, pady=(8, 0))

        # Voice Testing section
        voice_frame = ttk.LabelFrame(scrollable_frame, text="🎙️ Voice Testing", style="Card.TLabelframe")
        voice_frame.pack(fill="x", padx=15, pady=(0, 12))
        voice_frame.columnconfigure(0, weight=1)
        voice_frame.configure(padding=10)

        # Voice selection
        voice_select_frame = ttk.Frame(voice_frame, style="Modern.TFrame")
        voice_select_frame.pack(fill="x", padx=12, pady=(12, 8))
        voice_select_frame.columnconfigure(1, weight=1)
        
        ttk.Label(voice_select_frame, text="Voice:", font=("Segoe UI", 9), background="#f8fafc").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.voice_combo = ttk.Combobox(voice_select_frame, textvariable=self.voice_var, state="readonly", font=("Segoe UI", 10))
        self.voice_combo["values"] = [v.name for v in self.available_voices]
        self.voice_combo.grid(row=0, column=1, sticky="ew")
        self.voice_combo.bind("<<ComboboxSelected>>", lambda e: self._save_voice_selection())
        self.voice_combo.bind("<Double-1>", lambda e: self._open_voice_folder_clicked())
        
        # Test Text section
        test_frame = ttk.Frame(voice_frame, style="Modern.TFrame")
        test_frame.pack(fill="x", padx=12, pady=(0, 8))
        test_frame.columnconfigure(1, weight=1)

        ttk.Checkbutton(test_frame, text="Random", variable=self.random_var, command=self._on_random_toggle).grid(row=0, column=0, padx=(0, 10), sticky="n")
        
        self.test_entry = tk.Text(test_frame, height=3, wrap="word", font=("Segoe UI", 10))
        self.test_entry.grid(row=0, column=1, sticky="ew")
        
        test_scroll = ttk.Scrollbar(test_frame, command=self.test_entry.yview)
        test_scroll.grid(row=0, column=2, sticky="ns")
        self.test_entry.configure(yscrollcommand=test_scroll.set)

        # Bindings for Enter and Shift+Enter
        self.test_entry.bind("<Return>", self._on_test_entry_return)
        
        voice_btns = ttk.Frame(voice_frame, style="Modern.TFrame")
        voice_btns.pack(fill="x", padx=12, pady=(8, 4))
        
        ttk.Button(voice_btns, text="🔊 Test Voice", command=self._test_clicked, width=14, style="Accent.TButton").grid(row=0, column=0, padx=(0, 8))
        self.stop_audio_btn = ttk.Button(voice_btns, text="⏹ Stop", command=self._stop_audio_clicked, state="disabled", width=10)
        self.stop_audio_btn.grid(row=0, column=1, padx=(0, 8))
        ttk.Button(voice_btns, text="📥 Download", command=self._download_clicked, width=14).grid(row=0, column=2, padx=(0, 8))
        ttk.Button(voice_btns, text="📜 Voice Guide", command=self._open_voice_guide, width=14).grid(row=0, column=3, padx=(0, 8))

        self.loading_label = ttk.Label(voice_btns, text="", foreground="#3b82f6", background="#f8fafc", font=("Segoe UI", 9, "italic"))
        self.loading_label.grid(row=0, column=4, padx=(12, 0))

        # Initial toggle state
        self._on_random_toggle()

        # Preferences section (new - consolidates settings)
        prefs = ttk.LabelFrame(scrollable_frame, text="⚙️ Preferences", style="Card.TLabelframe")
        prefs.pack(fill="x", padx=15, pady=(0, 12))
        prefs.columnconfigure(0, weight=1)
        prefs.configure(padding=10)

        # Desktop shortcut option
        ttk.Checkbutton(prefs, text="🔗 Keep a shortcut to this Manager on my Desktop", 
                       variable=self.desktop_shortcut_var, command=self._save_settings, style="TCheckbutton").pack(anchor="w", padx=12, pady=(12, 4))
        ttk.Label(prefs, text="(Creates a desktop icon that opens this Manager window)", 
                 font=("Segoe UI", 8), foreground="#64748b", background="#f8fafc").pack(anchor="w", padx=32, pady=(0, 12))
        
        ttk.Button(prefs, text="🗑 Remove Desktop Shortcut", 
                  command=self._remove_desktop_shortcut_clicked, width=30).pack(anchor="w", padx=12, pady=(0, 8))

        # Collapsible Training section toggle
        training_toggle_frame = ttk.LabelFrame(scrollable_frame, text="⚙️ Advanced Options", style="Card.TLabelframe")
        training_toggle_frame.pack(fill="x", padx=15, pady=(0, 12))
        training_toggle_frame.configure(padding=10)
        
        ttk.Checkbutton(
            training_toggle_frame, 
            text="🧪 Show Legacy Voice Training Tools",
            variable=self.show_training_var,
            command=self._toggle_training_section
        ).pack(anchor="w", padx=12, pady=(10, 4))
        
        ttk.Label(
            training_toggle_frame,
            text="💡 Voice training is now available in the Web UI with a better interface.\nThis legacy section is for advanced users only.",
            font=("Segoe UI", 8),
            foreground="#666",
            justify=tk.LEFT
        ).pack(anchor="w", padx=32, pady=(0, 10))

        # Training section (collapsible)
        self.training_frame = ttk.LabelFrame(scrollable_frame, text="🧠 Voice Training (4-Step Process)", style="Card.TLabelframe")
        # Don't pack it initially - will be shown/hidden by toggle
        self.training_frame.columnconfigure(1, weight=1)
        self.training_frame.configure(padding=10)
        training = self.training_frame  # Keep reference for existing code

        guide_text = "1. [New Project] -> 2. [Split/Add Audio] -> 3. [Transcribe] -> 4. [Train]"
        ttk.Label(training, text=guide_text, font=("Segoe UI", 9, "italic"), foreground="#3b82f6").pack(anchor="w", padx=8, pady=(6, 2))
        
        # Row 1: Project Selection
        proj_frame = ttk.Frame(training)
        proj_frame.pack(fill="x", padx=8, pady=2)
        proj_frame.columnconfigure(1, weight=1)

        ttk.Label(proj_frame, text="Active Voice:").grid(row=0, column=0, sticky="w")
        self.training_project_var = tk.StringVar()
        self.training_project_combo = ttk.Combobox(proj_frame, textvariable=self.training_project_var, state="readonly")
        self.training_project_combo.grid(row=0, column=1, sticky="ew", padx=8)
        self.training_project_combo.bind("<Double-1>", lambda e: self._open_dojo_folder_clicked())
        
        self.refresh_training_btn = ttk.Button(proj_frame, text="Refresh", width=8, command=self._refresh_training_projects)
        self.refresh_training_btn.grid(row=0, column=2)

        self.storage_btn = ttk.Button(proj_frame, text="🗄️ Storage", width=12, command=self._open_storage_manager_clicked)
        self.storage_btn.grid(row=0, column=3, padx=(5, 0))

        # Row 2: Actions
        train_btns = ttk.Frame(training)
        train_btns.pack(fill="x", padx=8, pady=8)
        
        ttk.Button(train_btns, text="Step 1: New Voice", command=self._create_new_voice_clicked).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(train_btns, text="Step 2a: Split Long File", command=self._auto_split_clicked).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(train_btns, text="Step 2b: dataset/", command=self._open_dataset_folder_clicked).grid(row=0, column=2, padx=(0, 8))
        ttk.Button(train_btns, text="📁 Dojo Root", command=self._open_dojo_folder_clicked).grid(row=0, column=3, padx=(0, 8))
        ttk.Button(train_btns, text="Step 3: Transcribe", command=self._auto_transcribe_clicked).grid(row=0, column=4, padx=(0, 8))
        ttk.Button(train_btns, text="Step 4: Train", command=self._start_training_clicked).grid(row=0, column=5, padx=(0, 8))
        ttk.Button(train_btns, text="Step 5: Web UI 🚀", command=self._open_web_dashboard).grid(row=0, column=6, padx=(0, 8))

        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(training, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill="x", padx=8, pady=(0, 8))
        self.progress_label = ttk.Label(training, text="")
        self.progress_label.pack(anchor="e", padx=8, pady=(0, 8))
        
        self._refresh_training_projects()

        # Log section (now part of scrollable content)
        log_frame = ttk.LabelFrame(scrollable_frame, text="📋 Activity Log", style="Card.TLabelframe")
        log_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        log_frame.configure(padding=10)

        self.log = tk.Text(log_frame, height=14, wrap="word", state="disabled", font=("Consolas", 9), 
                          bg="#f8fafc", fg="#1e293b", relief="flat", borderwidth=1, highlightthickness=1, 
                          highlightbackground="#e2e8f0", highlightcolor="#3b82f6")
        self.log.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

        scrollbar = ttk.Scrollbar(log_frame, command=self.log.yview)
        scrollbar.grid(row=0, column=1, sticky="ns", pady=8, padx=(0, 8))
        self.log.configure(yscrollcommand=scrollbar.set)

        log_ctrls = ttk.Frame(log_frame)
        log_ctrls.grid(row=1, column=0, columnspan=2, sticky="e", padx=8, pady=(0, 8))
        ttk.Button(log_ctrls, text="📋 Copy Log", width=14, command=self._copy_log_clicked).pack(side="left", padx=4)
        ttk.Button(log_ctrls, text="🗑️ Clear Log", width=14, command=self._clear_log_clicked).pack(side="left", padx=4)

        log_to(self.log, f"Working directory: {SCRIPT_DIR}")
        log_to(self.log, f"Found {len(self.available_voices)} voice(s): {', '.join(v.name for v in self.available_voices)}")

    def _clear_log_clicked(self) -> None:
        """Clears the manager's system log."""
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _copy_log_clicked(self) -> None:
        """Copies the contents of the manager log to the system clipboard."""
        try:
            content = self.log.get("1.0", tk.END)
            self.master.clipboard_clear()
            self.master.clipboard_append(content)
            log_to(self.log, "Log copied to clipboard.", save_to_file=False)
        except Exception as e:
            log_to(self.log, f"Failed to copy log: {e}")

    def _thread(self, fn):
        t = threading.Thread(target=fn, daemon=True)
        t.start()

    def _base_url(self) -> str:
        host = self.host_var.get().strip() or DEFAULT_HOST
        port = int(self.port_var.get() or DEFAULT_PORT)
        return f"http://{host}:{port}"

    def _refresh_autostart(self) -> None:
        installed, label = autostart_query()
        self.autostart_var.set(f"Autostart: {label}")
        self._autostart_style = "Badge.Running.TLabel" if installed else "Badge.Stopped.TLabel"
        if hasattr(self, "autostart_label"):
            self.autostart_label.configure(style=self._autostart_style)

    def _refresh_status(self) -> None:
        """
        Polls the Piper server's health endpoint and updates the UI status indicators.
        Implements auto-restart logic if the server disappears unexpectedly.
        """
        def work():
            base = self._base_url()
            is_running = False
            status_text = "● STOPPED"
            style_name = "Badge.Stopped.TLabel"
            
            try:
                # 10s timeout ensures we don't 'give up' on the server during high CPU synthesis
                info = http_get_json(f"{base}/health", timeout=10.0)
                if info.get("ok") is True:
                    status_text = "● RUNNING"
                    style_name = "Badge.Running.TLabel"
                    is_running = True
                    self._should_be_running = True
                else:
                    status_text = f"● ERROR: {info.get('error', 'unknown')}"
                    style_name = "Badge.Error.TLabel"
                    self._should_be_running = True
            except Exception:
                pass

            def update_ui():
                self.status_var.set(status_text)
                self._status_style = style_name
                if hasattr(self, "status_label"):
                    self.status_label.configure(style=self._status_style)

            self.master.after(0, update_ui)

            # --- Automatic Failure Recovery (Auto-Restart) ---
            # Optimization: Reduced safety throttle to 15s for snappier recovery.
            # Logic Fix: Do NOT restart if we are currently playing audio (prevents interrupting busy server).
            if self.auto_restart_var.get() and self._should_be_running and not is_running and not self.is_playing:
                now = time.time()
                if now - self._last_restart_time > 15:
                    log_to(self.log, "Critical: Service interruption detected. Initiating emergency auto-restart...")
                    self._last_restart_time = now
                    
                    try:
                        # Clear old process entirely before restarting
                        port = int(self.port_var.get() or DEFAULT_PORT)
                        stop_server_by_port(self.log, port)
                        time.sleep(1)
                        self._start_clicked() # Re-launch standard startup sequence
                    except Exception as e:
                        log_to(self.log, f"Recovery sequence failed: {e}")

        self._thread(work)

    def _schedule_status_refresh(self) -> None:
        """Periodic UI Update: Runs every 5 seconds to keep health badges current."""
        self._refresh_status()
        # Refresh every 5 seconds
        self.master.after(5000, self._schedule_status_refresh)

    def _on_random_toggle(self) -> None:
        """UI Logic: Toggles the custom text input box based on the 'Random' checkbox state."""
        if self.random_var.get():
            self.test_entry.configure(state="disabled", background="#f0f0f0")
        else:
            self.test_entry.configure(state="normal", background="white")

    def get_display_ip(self) -> str:
        """Get appropriate IP address for display (SearXNG pattern)."""
        if os.name == 'nt':
            return "127.0.0.1"
        try:
            # Try to get the real IP on Linux/WSL for better accessibility
            output = subprocess.check_output(['hostname', '-I']).decode().strip()
            if output:
                return output.split()[0]
        except Exception:
            pass
        return "127.0.0.1"

    def update_url_display(self) -> None:
        """Update the URL entry with current host/port."""
        if hasattr(self, 'url_entry'):
            display_ip = self.get_display_ip()
            port = self.port_var.get()
            self.url_entry.config(state="normal")
            self.url_entry.delete(0, tk.END)
            self.url_entry.insert(0, f"http://{display_ip}:{port}")
            self.url_entry.config(state="readonly")

    def copy_url(self) -> None:
        """Copy URL to clipboard with visual feedback (SearXNG pattern)."""
        if hasattr(self, 'url_entry') and hasattr(self, 'copy_url_btn'):
            self.master.clipboard_clear()
            self.master.clipboard_append(self.url_entry.get())
            self.master.update()
            self.copy_url_btn.config(text="✓ Copied!")
            self.master.after(1500, lambda: self.copy_url_btn.config(text="Copy"))

    def _open_voice_folder_clicked(self) -> None:
        """Opens the folder containing the currently selected voice model."""
        selected = self.voice_var.get()
        if not selected:
            return
            
        # Match name to our scanned list to get full path
        voice_path = next((v for v in self.available_voices if v.name == selected), None)
        if not voice_path:
            return
            
        try:
            target = voice_path.parent
            if os.name == "nt":
                os.startfile(str(target))
            else:
                opener = "open" if sys.platform == "darwin" else "xdg-open"
                subprocess.Popen([opener, str(target)])
        except Exception as e:
            log_to(self.log, f"Failed to open voice folder: {e}")

    def _on_test_entry_return(self, event):
        """
        Input Handler: Allows 'Enter' to trigger speech, 
        while 'Shift+Enter' remains for new lines in the text box.
        """
        # If Shift is NOT pressed, trigger test and break
        # If Shift IS pressed, do nothing (let default newline happen)
        if not (event.state & 0x0001): 
            self._test_clicked()
            return "break"
        return None

    def _animate_loading(self, step: int = 0) -> None:
        """UI Animation: Cycles 'Generating...' dots during active synthesis."""
        if not self._loading_active:
            self.loading_label.configure(text="")
            return
        
        dots = "." * (step % 4)
        self.loading_label.configure(text=f"Generating{dots}")
        self.master.after(400, lambda: self._animate_loading(step + 1))

    def _start_clicked(self) -> None:
        """Handler: Initiates the server startup sequence in a background thread."""
        if self.transition_state is not None:
            return  # Already starting or stopping, ignore click
        
        self.transition_state = 'STARTING'
        # Safety timeout: if server doesn't start in 15s, re-enable buttons
        self.master.after(15000, lambda: setattr(self, 'transition_state', None) if self.transition_state == 'STARTING' else None)
        
        self._should_be_running = True # Set intent flag for auto-restart
        def work():
            self.master.after(0, lambda: self.status_var.set("Status: starting..."))
            self.master.after(0, lambda: self.status_label.configure(style="Badge.Unknown.TLabel"))

            host = self.host_var.get().strip() or DEFAULT_HOST
            try:
                port = int(self.port_var.get() or DEFAULT_PORT)
            except ValueError:
                log_to(self.log, "UI Error: Invalid integer for port.")
                self.transition_state = None
                self.master.after(0, self._refresh_status)
                return

            ok = start_server_process(self.log, host, port)
            if ok:
                log_to(self.log, "Server process dispatched. Verifying endpoint...")
                self.transition_state = None  # Clear transition state on success
                # Models might have been downloaded, update scanner
                self.master.after(0, self._refresh_voices)
                time.sleep(2.5) # Wait for Uvicorn spin-up (increased to help slower systems)
                self.master.after(0, self._refresh_status)
                
                # Check if server actually started by verifying the endpoint
                time.sleep(1.0)
                base = f"http://{host}:{port}"
                try:
                    resp = http_get_json(f"{base}/health", timeout=3.0)
                    log_to(self.log, f"Server health check passed: {resp.get('status', 'unknown')}")
                except Exception as health_err:
                    log_to(self.log, f"WARNING: Server health check failed: {health_err}")
                    log_to(self.log, "Server may have crashed on startup. Checking logs...")
                    # Read last 20 lines of server log to diagnose startup failure
                    server_log_path = SCRIPT_DIR / "piper_server.log"
                    if server_log_path.exists():
                        try:
                            with open(server_log_path, "r", encoding="utf-8", errors="ignore") as f:
                                lines = f.readlines()
                                last_lines = lines[-20:] if len(lines) > 20 else lines
                                log_to(self.log, "\n=== Recent Server Errors ===")
                                for line in last_lines:
                                    log_to(self.log, line.rstrip())
                                log_to(self.log, "=== End of Server Errors ===")
                        except Exception as read_err:
                            log_to(self.log, f"Could not read server log: {read_err}")
            else:
                self.transition_state = None
                self.master.after(0, self._refresh_status)

        self._thread(work)

    def _stop_clicked(self) -> None:
        """Handler: Terminates the server and clears the restart intent flag."""
        if self.transition_state is not None:
            return  # Already starting or stopping, ignore click
        
        self.transition_state = 'STOPPING'
        # Safety timeout: if server doesn't stop in 10s, re-enable buttons
        self.master.after(10000, lambda: setattr(self, 'transition_state', None) if self.transition_state == 'STOPPING' else None)
        
        self._should_be_running = False # Prevents auto-restart from fighting the user
        self.status_var.set("Status: stopping...")
        self.status_label.configure(style="Badge.Unknown.TLabel")

        def work():
            try:
                port = int(self.port_var.get() or DEFAULT_PORT)
            except ValueError:
                log_to(self.log, "UI Error: Invalid integer for port.")
                self.transition_state = None
                return

            stop_server_by_port(self.log, port)
            self.transition_state = None  # Clear transition state on success
            self.master.after(500, self._refresh_status)

        self._thread(work)

    def _status_clicked(self) -> None:
        """Manual Status Check: Retrieves detailed /health JSON for debugging."""
        self.status_var.set("Status: checking...")
        self._status_style = "Badge.Unknown.TLabel"
        if hasattr(self, "status_label"):
            self.status_label.configure(style=self._status_style)

        def work():
            base = self._base_url()
            try:
                info = http_get_json(f"{base}/health")
                log_to(self.log, f"/health response:\n{json.dumps(info, indent=2)}")
            except urllib.error.HTTPError as e:
                # Handle standard HTTP errors (404, 500 etc.)
                body = e.read().decode("utf-8", errors="ignore") if hasattr(e, "read") else ""
                log_to(self.log, f"/health HTTP {e.code}:\n{body}")
            except Exception as e:
                log_to(self.log, f"/health unreachable: {e}")
            self.master.after(0, self._refresh_status)

        self._thread(work)

    def _split_text(self, text: str) -> list[str]:
        """
        Text Pre-processing: Breaks long blocks into individual sentences.
        Sentences are streamed to the server one by one to achieve ultra-low 'time to first sound'.
        Optimization: Added protections for honorifics (Mr., Dr.) and decimals (1.0).
        """
        # Split on [.!?] followed by space, using multiple lookbehinds to ignore abbreviations.
        # Python's 're' requires fixed-width lookbehinds.
        pattern = (
            r'(?<!Mr)(?<!mr)(?<!Dr)(?<!dr)(?<!Ms)(?<!ms)(?<!Mrs)(?<!mrs)'
            r'(?<!Prof)(?<!prof)(?<!Sr)(?<!sr)(?<!Jr)(?<!jr)'
            r'(?<!\d)' # Avoid splitting on decimals like 1.0
            r'(?<=[.!?])\s+'
        )
        sentences = re.split(pattern, text.strip())
        
        chunks = []
        for s in sentences:
            s = s.strip()
            if not s:
                continue
            # Further break down very long run-on sentences by commas to keep buffers small
            if len(s) > 250:
                sub_chunks = re.split(r'(?<=,)\s+', s)
                for sc in sub_chunks:
                    sc = sc.strip()
                    if sc:
                        chunks.append(sc)
            else:
                chunks.append(s)
        return chunks

    def _test_clicked(self) -> None:
        """
        Main TTS Workflow: 
        1. Splits text into manageable chunks.
        2. Streams chunks to server from one thread.
        3. Plays audio as it arrives from a second thread.
        Optimization: Improved Windows duration calculation with jitter buffer.
        """
        # Ensure server is actually active before burning cycles
        if "running" not in self.status_var.get().lower():
            log_to(self.log, "Operation Blocked: Server is not active. Discarding request.")
            self._thread(lambda: self.master.after(0, self._refresh_status))
            return

        def work():
            # Interrupt any active sounds
            if self.is_playing:
                self._stop_audio_clicked()
                time.sleep(0.2)
            
            base = self._base_url()
            url = f"{base}/api/tts"
            
            # Select phrase source
            if self.random_var.get():
                test_messages = [
                    "Hey there! I'm Piper, your friendly text-to-speech assistant!",
                    "Testing one two three! Sounds great, doesn't it?",
                    "Hello! I can speak anything you type. Pretty cool, right?",
                    "Beep boop! Just kidding, I'm much better than a robot!",
                    "Ready to chat? I'm all ears... well, actually all voice!",
                ]
                import random
                test_msg = random.choice(test_messages)
            else:
                test_msg = self.test_entry.get("1.0", "end-1c").strip()
                if not test_msg:
                    test_msg = "Please enter some text for me to voice."
            
            selected_voice = (self.voice_var.get() or "").strip()
            chunks = self._split_text(test_msg)
            
            log_to(self.log, f"TTS Request: Processing {len(chunks)} chunk(s) via '{selected_voice or 'Standard'}'")
            
            self.is_playing = True
            # Activate UI 'Stop' button
            self.master.after(0, lambda: self.stop_audio_btn.configure(state="normal"))
            
            # Pipeline: [Producer: Fetcher Thread] -> [Queue] -> [Consumer: Player Thread]
            audio_queue = queue.Queue(maxsize=2) # Only buffer 2 chunks ahead to save RAM
            
            def fetcher():
                """Background task: Requests WAVE files for each text chunk."""
                try:
                    for i, chunk in enumerate(chunks):
                        if not self.is_playing:
                            break # User clicked Stop
                        
                        payload = {"text": chunk}
                        if selected_voice:
                            payload["voice_model"] = selected_voice
                        
                        # Only show the 'Generating' indicator for the first chunk to minimize UI flicker
                        if i == 0:
                            self._loading_active = True
                            self.master.after(0, self._animate_loading)
                        
                        try:
                            wav_bytes = http_post_json(url, payload)
                            if i == 0:
                                # Stop animation once the first sound is ready
                                self._loading_active = False
                            audio_queue.put(wav_bytes)
                        except Exception as e:
                            log_to(self.log, f"Fetcher Error (Chunk {i+1}): {e}")
                            if i == 0:
                                self._loading_active = False
                            break
                finally:
                    audio_queue.put(None) # Signal the Player thread that we are done

            self._thread(fetcher)

            # Audio Playback Loop (Current Work Thread)
            try:
                while self.is_playing:
                    wav_bytes = audio_queue.get()
                    if wav_bytes is None:
                        break # Queue signaling end of text
                    
                    # Store bytes in temporary file for playback libraries
                    import tempfile
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
                        temp_wav = f.name
                        f.write(wav_bytes)
                    
                    try:
                        # Cross-platform audio playback
                        self.playback_process = audio_playback.play_wav_async(temp_wav)
                        # Optimization: Added 50ms jitter buffer to ensure driver clears before next chunk
                        duration = audio_playback.get_wav_duration(temp_wav) + 0.05
                        
                        # Block the thread for the duration of the audio clip
                        start_time = time.time()
                        while time.time() - start_time < duration and self.is_playing:
                            time.sleep(0.05) # Higher polling frequency for tighter timing

                    except Exception as play_err:
                        log_to(self.log, f"Audio Driver Failure: {play_err}")
                    finally:
                        # Ensure temp file is purged regardless of playback success
                        try:
                            os.remove(temp_wav)
                        except Exception:
                            pass
                
                log_to(self.log, f"TTS Sequence Finished: {len(chunks)} chunk(s) voiced.")

            except Exception as e:
                log_to(self.log, f"Critical Playback Error: {e}")
            finally:
                self.is_playing = False
                self.master.after(0, lambda: self.stop_audio_btn.configure(state="disabled"))

        self._thread(work)

    def _download_clicked(self) -> None:
        """
        Action: Triggers a WAV download of the current text.
        The server generates the file and the UI presents a 'Save As' dialog.
        """
        # Pre-flight check: server must be running to generate the audio bytes
        if "running" not in self.status_var.get().lower():
            log_to(self.log, "Operation Blocked: Server is not active. Discarding request.")
            self._thread(lambda: self.master.after(0, self._refresh_status))
            return

        def work():
            base = self._base_url()
            url = f"{base}/api/tts"
            
            # Determine text to say
            if self.random_var.get():
                test_messages = [
                    "Hey there! I'm Piper, your friendly text-to-speech assistant!",
                    "Testing one two three! Sounds great, doesn't it?",
                    "Hello! I can speak anything you type. Pretty cool, right?",
                    "Beep boop! Just kidding, I'm much better than a robot!",
                    "Ready to chat? I'm all ears... well, actually all voice!",
                ]
                import random
                test_msg = random.choice(test_messages)
            else:
                test_msg = self.test_entry.get("1.0", "end-1c").strip()
                if not test_msg:
                    test_msg = "There is no text for me to say"
            
            selected_voice = (self.voice_var.get() or "").strip()
            
            log_to(self.log, f"Downloading TTS with voice: {selected_voice or '(default)'}")
            log_to(self.log, f"Text: \"{test_msg}\"")
            
            # Show loading indicator
            self._loading_active = True
            self.master.after(0, self._animate_loading)
            
            try:
                payload = {"text": test_msg}
                if selected_voice:
                    payload["voice_model"] = selected_voice

                wav_bytes = http_post_json(url, payload)
                
                # Hide loading indicator
                self._loading_active = False
                
                # Ask user where to save
                self.master.after(0, lambda: self._save_wav_dialog(wav_bytes, test_msg))
                    
            except urllib.error.HTTPError as e:
                self._loading_active = False
                body = e.read().decode("utf-8", errors="ignore") if hasattr(e, "read") else ""
                log_to(self.log, f"TTS download HTTP {e.code}:\n{body}")
            except Exception as e:
                self._loading_active = False
                log_to(self.log, f"TTS download failed: {e}")

        self._thread(work)

    def _save_wav_dialog(self, wav_bytes: bytes, text: str) -> None:
        """Open a save dialog and write the WAV bytes to disk."""
        # Create a filename with a timestamp
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        default_filename = f"Piper TTS ({timestamp}).wav"
            
        file_path = filedialog.asksaveasfilename(
            defaultextension=".wav",
            filetypes=[("WAV files", "*.wav"), ("All files", "*.*")],
            initialfile=default_filename,
            title="Save TTS Audio"
        )
        
        if file_path:
            try:
                with open(file_path, "wb") as f:
                    f.write(wav_bytes)
                log_to(self.log, f"Successfully saved audio to: {file_path}")
            except Exception as e:
                log_to(self.log, f"Failed to save file: {e}")
        else:
            log_to(self.log, "Download cancelled by user.")

    def _stop_audio_clicked(self) -> None:
        """
        Interrupts all active or queued audio playback immediately.
        Handles process termination for Linux/Mac and stream purging for Windows.
        """
        self.is_playing = False # Consumer loop in _test_clicked will see this and exit
        
        # Cross-platform audio stop
        try:
            audio_playback.stop_playback(self.playback_process)
            self.playback_process = None
        except Exception:
            pass

        self.stop_audio_btn.configure(state="disabled")
        log_to(self.log, "Audio interruption successful. Playback halted.")

    def _install_autostart_clicked(self) -> None:
        """Handler: Configures the OS to launch Piper on login."""
        def work():
            autostart_install(self.log)
            self.master.after(0, self._refresh_autostart)

        self._thread(work)

    def _toggle_startup(self) -> None:
        """Handler: Toggle startup shortcut based on checkbox state."""
        def work():
            if self.launch_on_startup_var.get():
                # Enable startup
                autostart_install(self.log)
            else:
                # Disable startup
                autostart_uninstall(self.log)
            # Update status
            enabled, msg = autostart_query()
            self.master.after(0, lambda: log_to(self.log, f"Autostart status: {msg}"))

        self._thread(work)

    def _update_startup_shortcut(self) -> None:
        """Create or remove startup shortcut based on user preference (SearXNG pattern)."""
        if os.name != 'nt':
            return  # Only Windows for now
        
        startup_shortcut_path = _startup_shortcut_path()
        
        if self.launch_on_startup_var.get():
            # User wants startup - create shortcut if it doesn't exist
            if startup_shortcut_path.exists():
                return  # Already exists, nothing to do
            
            launcher_vbs = SCRIPT_DIR.parent / "launchers" / "Open Piper Server.vbs"
            if not launcher_vbs.exists():
                return  # Can't create without launcher
            
            # Ensure startup directory exists
            startup_shortcut_path.parent.mkdir(parents=True, exist_ok=True)
            
            ps_cmd = (
                f"$WshShell = New-Object -ComObject WScript.Shell; "
                f"$Shortcut = $WshShell.CreateShortcut('{str(startup_shortcut_path)}'); "
                f"$Shortcut.TargetPath = '{str(launcher_vbs)}'; "
                f"$Shortcut.WorkingDirectory = '{str(SCRIPT_DIR.parent)}'; "
                f"$Shortcut.WindowStyle = 7; "  # 7 = Minimized
                f"$Shortcut.Save()"
            )
            
            try:
                subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], 
                             check=False, capture_output=True, **({'creationflags': 0x08000000} if os.name == 'nt' else {}))
            except Exception:
                pass
        else:
            # User doesn't want startup - remove shortcut if it exists
            if startup_shortcut_path.exists():
                try:
                    startup_shortcut_path.unlink()
                except Exception:
                    pass

    def _update_desktop_shortcut(self) -> None:
        """Create or remove desktop shortcut based on user preference (SearXNG pattern)."""
        if os.name != 'nt':
            return  # Only Windows for now
        
        desktop_shortcut_path = Path(os.environ.get('USERPROFILE', '')) / "Desktop" / "PiperTTS Mockingbird.lnk"
        
        if self.desktop_shortcut_var.get():
            # User wants the shortcut - create it if it doesn't exist
            if desktop_shortcut_path.exists():
                return  # Already exists, nothing to do
            
            launcher_vbs = SCRIPT_DIR.parent / "Open PiperTTS Mockingbird (Windows).vbs"
            if not launcher_vbs.exists():
                return  # Can't create without launcher
            
            # Try to use PiperTTS Mockingbird icon if available, otherwise use Windows microphone icon
            icon_path = SCRIPT_DIR.parent / "assets" / "mockingbird.ico"
            if icon_path.exists():
                icon_location = f"{str(icon_path)}, 0"
            else:
                # Fallback to Windows shell32.dll icon
                # Icon 44 is a microphone icon in shell32.dll (perfect for TTS/voice app)
                icon_location = "shell32.dll, 44"
            
            ps_cmd = (
                f"$WshShell = New-Object -ComObject WScript.Shell; "
                f"$Shortcut = $WshShell.CreateShortcut('{str(desktop_shortcut_path)}'); "
                f"$Shortcut.TargetPath = '{str(launcher_vbs)}'; "
                f"$Shortcut.WorkingDirectory = '{str(SCRIPT_DIR.parent)}'; "
                f"$Shortcut.IconLocation = '{icon_location}'; "
                f"$Shortcut.Description = 'PiperTTS Mockingbird Manager'; "
                f"$Shortcut.Save()"
            )
            
            try:
                subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], 
                             check=False, capture_output=True, **({'creationflags': 0x08000000} if os.name == 'nt' else {}))
            except Exception:
                pass
        else:
            # User doesn't want the shortcut - remove it if it exists
            if desktop_shortcut_path.exists():
                try:
                    desktop_shortcut_path.unlink()
                except Exception:
                    pass

    def _remove_desktop_shortcut_clicked(self) -> None:
        """Handler: Remove desktop shortcut button."""
        # Just uncheck the box and save - the save handler will remove the shortcut
        self.desktop_shortcut_var.set(False)
        self._save_settings()

    def _uninstall_autostart_clicked(self) -> None:
        """Handler: Removes Piper from the system startup sequence."""
        def work():
            autostart_uninstall(self.log)
            self.master.after(0, self._refresh_autostart)

        self._thread(work)

    def _load_settings(self) -> None:
        """
        Persistence: Reads previous session configuration from config.json.
        Applies defaults if no configuration is found.
        """
        cfg = load_config()
        
        # UI State Restoration: Voice selection
        selected = cfg.get("voice_model", "")
        if selected and any(v.name == selected for v in self.available_voices):
            self.voice_var.set(selected)
        elif self.available_voices:
            # Fallback to the first available voice alphabetically
            self.voice_var.set(self.available_voices[0].name)
            
        # UI State Restoration: Checkboxes
        self.auto_restart_var.set(cfg.get("auto_restart", False))
        # Load startup preference (default True for new installs)
        self.launch_on_startup_var.set(cfg.get("launch_on_startup", True))
        # Load desktop shortcut preference (default True for new installs)
        self.desktop_shortcut_var.set(cfg.get("desktop_shortcut", True))
        # Create/remove shortcuts based on preferences
        self._update_startup_shortcut()
        self._update_desktop_shortcut()

    def _save_settings(self) -> None:
        """Persistence: Commits the current UI configuration to disk."""
        cfg = load_config()
        cfg["voice_model"] = self.voice_var.get()
        cfg["host"] = self.host_var.get()
        cfg["port"] = self.port_var.get()
        cfg["auto_restart"] = self.auto_restart_var.get()
        cfg["launch_on_startup"] = self.launch_on_startup_var.get()
        cfg["desktop_shortcut"] = self.desktop_shortcut_var.get()
        self._update_startup_shortcut()
        self._update_desktop_shortcut()
        self.update_url_display()  # Update URL when port changes
        save_config(cfg)

    def _save_voice_selection(self) -> None:
        """Handler: Triggered whenever the user picks a new voice from the list."""
        self._save_settings()
        log_to(self.log, f"Profile Switch: Service now using '{self.voice_var.get()}'.")
        log_to(self.log, "Note: Voice swap is handled server-side during the next inference.")

    def _refresh_training_projects(self) -> None:
        """
        Scanner: Looks for directory structures matching the 'Dojo' pattern.
        A 'Dojo' is a workspace for a specific custom voice project.
        """
        dojo_dir = SCRIPT_DIR.parent / "training" / "make piper voice models" / "tts_dojo"
        projects = []
        if dojo_dir.exists():
            for item in dojo_dir.iterdir():
                # A valid project folder must follow the <name>_dojo naming convention
                if item.is_dir() and item.name.endswith("_dojo"):
                    projects.append(item.name)
        
        self.training_project_combo["values"] = sorted(projects)
        if projects and not self.training_project_var.get():
            self.training_project_var.set(projects[0])
        elif not projects:
            self.training_project_var.set("")

    def _get_project_settings(self, name: str):
        """Prompt user for quality and gender for a new voice."""
        from tkinter import messagebox
        import tkinter.simpledialog as sd
        
        # Gender Selection
        gender_win = tk.Toplevel(self.master)
        gender_win.title(f"Settings for {name}")
        gender_win.geometry("380x480") # Generous default size
        gender_win.minsize(350, 400)   # Ensure enough space for content
        gender_win.grab_set()

        # Add a scrollable container for smaller screens or future expansion
        container = tk.Frame(gender_win)
        container.pack(fill="both", expand=True)

        canvas = tk.Canvas(container)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )

        window_id = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        
        # Handle canvas resizing to fill frame width
        def _on_canvas_configure(event):
            canvas.itemconfig(window_id, width=event.width)
        canvas.bind("<Configure>", _on_canvas_configure)

        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        tk.Label(scrollable_frame, text=f"Configure {name}", font=("Segoe UI", 12, "bold")).pack(pady=10)
        
        tk.Label(scrollable_frame, text="Voice Gender:").pack()
        gender_var = tk.StringVar(value="female")
        tk.Radiobutton(scrollable_frame, text="Female (Lessac)", variable=gender_var, value="female").pack()
        tk.Radiobutton(scrollable_frame, text="Male (Ryan/Adam)", variable=gender_var, value="male").pack()

        tk.Label(scrollable_frame, text="\nModel Quality:").pack()
        quality_var = tk.StringVar(value="M")
        tk.Radiobutton(scrollable_frame, text="Medium (Balanced)", variable=quality_var, value="M").pack()
        tk.Radiobutton(scrollable_frame, text="High (Best Detail)", variable=quality_var, value="H").pack()
        tk.Radiobutton(scrollable_frame, text="Low (Fastest)", variable=quality_var, value="L").pack()

        result = {"gender": "female", "quality": "M"}
        
        def on_ok():
            result["gender"] = gender_var.get()
            result["quality"] = quality_var.get()
            gender_win.destroy()

        tk.Button(scrollable_frame, text="Create Dojo", command=on_ok, width=20, bg="#28a745", fg="white").pack(pady=20)
        
        self.master.wait_window(gender_win)
        return result

    def _create_new_voice_clicked(self) -> None:
        """
        [STEP 1] AUTO-TRAIN FLOW: Create New Voice Project
        
        This is the entry point for the training workflow.
        1. Prompts user for a voice name (e.g., "jarvis").
        2. Prompts for Quality/Gender settings.
        3. Executes `new_dojo.ps1 voice quality gender` to create the folder structure.
        4. Automatically advances to Step 2 (Dataset Slicer) via `_auto_split_clicked`.
        """
        from tkinter import simpledialog
        raw_name = simpledialog.askstring("New Voice", "Enter a name for your voice (no spaces):")
        if not raw_name:
            return
            
        try:
            # Strictly validate the name using the common utility
            voice_name = validate_voice_name(raw_name)
        except ValueError as e:
            from tkinter import messagebox
            messagebox.showerror("Invalid Name", str(e))
            return

        # Get specifics
        settings = self._get_project_settings(voice_name)
        
        training_dir = SCRIPT_DIR.parent / "training" / "make piper voice models"
        script = training_dir / "new_dojo.ps1"
        
        def work():
            log_to(self.log, f"Creating new voice: {voice_name} ({settings['gender']}, {settings['quality']})...")
            # Run the PowerShell script that scaffolds the directory (tts_dojo/<name>_dojo)
            # Now passing params: voice_name, quality, gender
            cmd = f"cd '{training_dir}'; ./new_dojo.ps1 {voice_name} {settings['quality']} {settings['gender']}"
            code, out = powershell(cmd)
            if code == 0:
                log_to(self.log, f"Successfully created {voice_name}.")
                self.master.after(0, self._refresh_training_projects)
                self.master.after(0, lambda: self.training_project_var.set(f"{voice_name}_dojo"))
                # [AUTO-ADVANCE] Automatically launch the Dataset Slicer to start adding audio
                self.master.after(0, self._auto_split_clicked)
            else:
                log_to(self.log, f"Error creating voice: {out}")

        self._thread(work)

    def _open_dataset_folder_clicked(self) -> None:
        """Open the dataset folder for the currently selected project."""
        project = self.training_project_var.get()
        if not project:
            log_to(self.log, "Error: No project selected.")
            return
            
        dataset_path = SCRIPT_DIR.parent / "training" / "make piper voice models" / "tts_dojo" / project / "dataset"
        if not dataset_path.exists():
            dataset_path.mkdir(parents=True, exist_ok=True)
            
        try:
            if os.name == "nt":
                os.startfile(str(dataset_path))
            else:
                opener = "open" if sys.platform == "darwin" else "xdg-open"
                subprocess.Popen([opener, str(dataset_path)])
        except Exception as e:
            log_to(self.log, f"Failed to open folder: {e}")

    def _open_dojo_folder_clicked(self) -> None:
        """Open the root dojo folder for the currently selected project."""
        project = self.training_project_var.get()
        if not project:
            log_to(self.log, "Error: No project selected.")
            return
            
        dojo_path = SCRIPT_DIR.parent / "training" / "make piper voice models" / "tts_dojo" / project
        if not dojo_path.exists():
            log_to(self.log, f"Error: Folder does not exist: {dojo_path}")
            return
            
        try:
            if os.name == "nt":
                os.startfile(str(dojo_path))
            else:
                opener = "open" if sys.platform == "darwin" else "xdg-open"
                subprocess.Popen([opener, str(dojo_path)])
        except Exception as e:
            log_to(self.log, f"Failed to open dojo folder: {e}")

    def _auto_split_clicked(self) -> None:
        """
        [STEP 2] AUTO-TRAIN FLOW: Launch Dataset Slicer
        
        This tool allows the user to split long audio files into short samples.
        1. Identifies the target dataset directory: `tts_dojo/<voice>_dojo/dataset`.
        2. Launches `dataset_slicer_ui.py` as a separate process.
        3. Passes the target directory and voice name as arguments so the tool knows where to save files.
        """
        project = self.training_project_var.get()
        if not project:
            log_to(self.log, "Error: No project selected.")
            return

        # Path to dataset folder (optional, if we want to pre-set export path eventually)
        dataset_path = SCRIPT_DIR.parent / "training" / "make piper voice models" / "tts_dojo" / project / "dataset"
        
        # Path to slicer tool
        slicer_script = SCRIPT_DIR / "tools" / "dataset_slicer_ui.py"
        
        if not slicer_script.exists():
            log_to(self.log, f"Error: Slicer tool not found at {slicer_script}")
            return
            
        log_to(self.log, "Launching Dataset Slicer Tool...")
        log_to(self.log, f"Tip: Use the tool to manually slice clips, then export them to: {dataset_path}")

        def launch():
            # Run detached so it doesn't block this UI
            cmd = [str(slicer_script), "--dataset_dir", str(dataset_path), "--voice_name", project]
            if os.name == 'nt':
                # pythonw.exe to avoid console window
                python_exe = str(VENV_PYTHONW) if VENV_PYTHONW.exists() else str(VENV_PYTHON)
                creation_flags = subprocess.CREATE_NO_WINDOW
                subprocess.Popen([python_exe] + cmd, creationflags=creation_flags, cwd=str(SCRIPT_DIR))
            else:
                subprocess.Popen([str(VENV_PYTHON)] + cmd, cwd=str(SCRIPT_DIR))

        self.master.after(0, launch)


    def _auto_transcribe_clicked(self) -> None:
        """
        [STEP 3] AUTO-TRAIN FLOW: Launch Transcribe Wizard
        
        This button now launches the dedicated Transcribe Wizard GUI (Step 3).
        """
        project = self.training_project_var.get()
        if not project:
            log_to(self.log, "Error: No project selected.")
            return
            
        dataset_path = SCRIPT_DIR.parent / "training" / "make piper voice models" / "tts_dojo" / project / "dataset"
        wizard_script = SCRIPT_DIR / "tools" / "transcribe_wizard.py"
        
        if not wizard_script.exists():
            log_to(self.log, f"Error: Transcription tool not found at {wizard_script}")
            return

        log_to(self.log, f"Launching Transcription Wizard for {project}...")
        
        def launch():
            python_exe = str(VENV_PYTHONW) if VENV_PYTHONW.exists() else str(VENV_PYTHON)
            cmd = [python_exe, str(wizard_script), "--dataset_dir", str(dataset_path), "--voice_name", project]
            
            try:
                creation_flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                subprocess.Popen(cmd, creationflags=creation_flags, cwd=str(SCRIPT_DIR))
            except Exception as e:
                log_to(self.log, f"Error launching wizard: {e}")

        self.master.after(0, launch)

    def _start_training_clicked(self) -> None:
        """
        [STEP 5 MANUAL] AUTO-TRAIN FLOW: Launch Training Dashboard
        
        This button launches the main Training Dashboard UI (Step 5).
        It is where the user selects the base model, quality settings, 
        and ultimately launches the Docker container.
        """
        project = self.training_project_var.get()
        if not project:
            log_to(self.log, "Error: No project selected to train.")
            return
            
        training_dash_script = SCRIPT_DIR / "training_dashboard_ui.py"
        
        log_to(self.log, f"Opening Training Dashboard for {project}...")
        
        try:
            if os.name == "nt":
                # Launch the training dashboard in pythonw (no console)
                python_exe = str(VENV_PYTHONW) if VENV_PYTHONW.exists() else str(VENV_PYTHON)
                # Pass the selected dojo as an argument? The dashboard currently doesn't accept args, 
                # but it defaults to selecting the dojo if only one is active, or user selects it.
                # For now, just launch it.
                subprocess.Popen([python_exe, str(training_dash_script), "--dojo", project], creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                subprocess.Popen([str(VENV_PYTHON), str(training_dash_script), "--dojo", project])
        except Exception as e:
            log_to(self.log, f"Failed to start training dashboard: {e}")

    def _open_voice_guide(self) -> None:
        """Opens the voice guide as a formatted HTML document in the browser."""
        guide_path = SCRIPT_DIR.parent / "voices" / "HOW_TO_ADD_VOICES.md"
        template_path = SCRIPT_DIR / "voice_guide_template.html"
        output_path = SCRIPT_DIR.parent / "docs" / "Voice_Guide.html"
        
        try:
            if not guide_path.exists():
                log_to(self.log, f"System Error: Documentation file missing at {guide_path}")
                return
                
            if not template_path.exists():
                log_to(self.log, f"System Error: HTML template missing at {template_path}")
                return
            
            # Use root as fallback if docs/ doesn't exist
            if not (SCRIPT_DIR.parent / "docs").exists():
                output_path = SCRIPT_DIR.parent / "Voice_Guide.html"
            
            # Read markdown content
            with open(guide_path, 'r', encoding='utf-8') as f:
                markdown_content = f.read()
            
            # Read HTML template
            with open(template_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            # Escape markdown for JavaScript injection
            json_safe_markdown = json.dumps(markdown_content)
            
            # Inject markdown directly into the HTML
            injection_code = f"""
            const markdownText = {json_safe_markdown};
            const contentDiv = document.getElementById('content');
            marked.use({{ gfm: true, breaks: true }});
            contentDiv.innerHTML = marked.parse(markdownText);
            generateTOC(); // Trigger TOC generation
            """
            
            # Replace the loadReadme() call with our injection
            new_html = html_content.replace("loadReadme();", injection_code)
            
            # Save to output directory
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(new_html)
            
            # Create file URI
            file_url = Path(output_path).absolute().as_uri()
            
            # WSL Special Handling
            try:
                with open('/proc/version', 'r') as f:
                    is_wsl = 'microsoft' in f.read().lower()
            except:
                is_wsl = False
            
            if is_wsl:
                try:
                    # Convert Linux path to Windows path
                    win_path = subprocess.check_output(['wslpath', '-w', str(output_path)]).strip().decode('utf-8')
                    subprocess.run(["explorer.exe", win_path], check=False)
                    return
                except Exception:
                    pass
            
            # Open in browser
            webbrowser.open(file_url)
            log_to(self.log, f"Voice guide opened in browser")
            
        except Exception as e:
            log_to(self.log, f"UI Error: Failed to open voice guide. {e}")

    def _toggle_training_section(self) -> None:
        """Shows or hides the legacy training section based on checkbox state."""
        if self.show_training_var.get():
            self.training_frame.pack(fill="x", padx=10, pady=(0, 10))
            log_to(self.log, "Legacy training section expanded")
        else:
            self.training_frame.pack_forget()
            log_to(self.log, "Legacy training section collapsed")

    def _open_storage_manager_clicked(self) -> None:
        """Launches the dedicated storage management tool."""
        storage_script = SCRIPT_DIR / "storage_manager_ui.py"
        if not storage_script.exists():
            log_to(self.log, f"Error: Storage manager script not found at {storage_script}")
            return

        log_to(self.log, "Opening Storage Manager...")
        try:
            python_exe = str(VENV_PYTHONW) if VENV_PYTHONW.exists() else str(VENV_PYTHON)
            if os.name == "nt":
                subprocess.Popen([python_exe, str(storage_script)], creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                subprocess.Popen([str(VENV_PYTHON), str(storage_script)])
        except Exception as e:
            log_to(self.log, f"Failed to start storage manager: {e}")

    def _open_web_dashboard(self) -> None:
        """Opens the HTML5 Web Dashboard in the default browser."""
        port = self.port_var.get()
        host = self.host_var.get()
        url = f"http://{host}:{port}"
        
        log_to(self.log, f"Opening Web Dashboard at {url}...")
        try:
            webbrowser.open(url)
        except Exception as e:
            log_to(self.log, f"Failed to open browser: {e}")


def main() -> None:
    """
    Bootstrap Section:
    1. Ensures only one copy of the manager is running.
    2. Initializes the Tkinter context and sets the session floor size.
    3. Triggers the main loop.
    """
    # Set Windows taskbar icon (must be done before creating Tk window)
    if os.name == 'nt':
        try:
            import ctypes
            # Set AppUserModelID to separate this app from Python in Windows taskbar
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('PiperTTS.Mockingbird.Manager')
        except:
            pass
    
    if not check_single_instance():
        # Port lock prevents duplicate processes which would cause port conflicts
        sys.exit(0)

    root = tk.Tk()
    root.configure(bg="#f8fafc")
    
    # Set window icon for taskbar (title bar icon will be small but necessary for taskbar)
    try:
        png_path = SCRIPT_DIR.parent / "assets" / "mockingbird.png"
        if png_path.exists():
            # Load and keep reference to prevent garbage collection
            icon_photo = tk.PhotoImage(file=str(png_path))
            root.iconphoto(True, icon_photo)
    except Exception as e:
        _write_ui_log(f"Failed to load window icon: {e}")
    
    App(root)
    # Start with a larger geometry so content is visible without scrolling
    root.geometry("1050x900")
    # Optimization: Increased default min-size to ensure Log visibility on High-DPI screens
    root.minsize(850, 650)
    
    root.mainloop()


if __name__ == "__main__":
    main()
