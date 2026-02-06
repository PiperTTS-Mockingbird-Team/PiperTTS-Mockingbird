from __future__ import annotations

import os
import sys
import time
import shutil
import traceback
from pathlib import Path

# Common utilities for sanitization and config management
from common_utils import validate_voice_name, safe_config_save, safe_config_load

# Import the downloader module
try:
    import download_piper
except ImportError:
    # Fallback if running from a different context, though SCRIPT_DIR should handle it
    sys.path.append(str(Path(__file__).resolve().parent))
    import download_piper

import audio_playback

# Define key paths relative to this script
SCRIPT_DIR = Path(__file__).resolve().parent
UI_LOG_PATH = SCRIPT_DIR / "piper_manager_ui.log"
CONFIG_PATH = SCRIPT_DIR / "config.json"
VENV_DIR = SCRIPT_DIR.parent / ".venv"

# Detect OS-specific virtual environment paths
if os.name == "nt":
    # Windows paths
    VENV_PYTHON = VENV_DIR / "Scripts" / "python.exe"
    VENV_PYTHONW = VENV_DIR / "Scripts" / "pythonw.exe"
else:
    # Linux/Mac paths
    VENV_PYTHON = VENV_DIR / "bin" / "python"
    VENV_PYTHONW = VENV_DIR / "bin" / "python"  # No pythonw on Linux/Mac

# Default server settings
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5002
RUN_KEY = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run"  # legacy (older versions)
RUN_VALUE_NAME = "Piper TTS Server"  # legacy (older versions)


def _write_ui_log(msg: str) -> None:
    """Write a message to the UI log file with a timestamp."""
    try:
        UI_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with UI_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
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


import json
import re
import socket
import subprocess
import threading
import queue
import urllib.error
import urllib.request

import tkinter as tk
from tkinter import ttk, filedialog

# Single instance check port
SINGLE_INSTANCE_PORT = 5003

def check_single_instance() -> bool:
    """Check if another instance is already running using a socket."""
    try:
        # Try to bind to the port
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(('127.0.0.1', SINGLE_INSTANCE_PORT))
        # Keep the socket open for the life of the process
        globals()['_instance_socket'] = s
        return True
    except socket.error:
        return False


def _startup_shortcut_path() -> Path:
    """Return the path to the startup shortcut/link for the current OS."""
    if os.name != "nt":
        # Not used on Mac/Linux, but return a dummy path to prevent errors if called
        return SCRIPT_DIR / "autostart_dummy"
        
    appdata = os.environ.get("APPDATA")
    if not appdata:
        # Fallback, should not happen on Windows.
        return SCRIPT_DIR / "PiperTTS Mockingbird.lnk"
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
    """Append a message to a Tkinter Text widget and optionally save to log file."""
    if save_to_file:
        _write_ui_log(msg)

    try:
        widget.configure(state="normal")
        widget.insert("end", f"[{_now()}] {msg}\n")
        widget.see("end")
        widget.configure(state="disabled")
    except Exception:
        pass


def run_cmd_capture(args: list[str], cwd: Path | None = None) -> tuple[int, str]:
    """Run a command and capture its output, suppressing the console window on Windows."""
    try:
        kwargs = {}
        if os.name == "nt":
            # CREATE_NO_WINDOW = 0x08000000
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
    """Run a command in real-time, streaming its output to a log widget and handling progress updates."""
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
            bufsize=1, # Line buffered
            **kwargs,
        )

        full_output = []
        if p.stdout:
            for line in iter(p.stdout.readline, ""):
                line_str = line.strip()
                if line_str.startswith("PROGRESS:"):
                    try:
                        # Format: PROGRESS:10/200
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
                    log_to(log_widget, line_str, save_to_file=False)
                full_output.append(line)
        
        p.stdout.close()
        return_code = p.wait()
        return return_code
    except Exception as e:
        log_to(log_widget, f"Error: {e}")
        return 1


def ensure_venv_and_deps(log: tk.Text) -> bool:
    """Ensure the virtual environment exists and all dependencies are installed."""
    # If venv exists but is Python 3.13+, it will fail (audioop missing for pydub)
    if VENV_PYTHON.exists():
        try:
            code, out = run_cmd_capture([str(VENV_PYTHON), "--version"])
            if " 3.13" in out or " 3.14" in out:
                log_to(log, "Existing venv is Python 3.13+ (incompatible). Recreating with 3.10...")
                shutil.rmtree(VENV_DIR, ignore_errors=True)
        except Exception:
            pass

    if not VENV_PYTHON.exists():
        log_to(log, f"Creating venv: {VENV_DIR}")
        
        # Prefer Python 3.10 for compatibility (audioop was removed in 3.13)
        python_exe = sys.executable
        possible_310 = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python" / "Python310" / "python.exe",
            Path("C:/Program Files/Python310/python.exe"),
            Path("C:/Python310/python.exe")
        ]
        for p in possible_310:
            if p.exists():
                python_exe = str(p)
                log_to(log, f"Using Python 3.10 found at: {python_exe}")
                break

        code, out = run_cmd_capture([python_exe, "-m", "venv", str(VENV_DIR)], cwd=SCRIPT_DIR)
        if code != 0:
            log_to(log, f"Failed to create venv (code {code}):\n{out}")
            return False

    req = SCRIPT_DIR / "requirements.txt"
    if not req.exists():
        log_to(log, "Missing requirements.txt; creating minimal one.")
        req.write_text("fastapi\nuvicorn\npydantic\n", encoding="utf-8")

    # Fast check: if we can import key packages, skip slow pip install
    code, _ = run_cmd_capture([str(VENV_PYTHON), "-c", "import fastapi; import uvicorn; import pydub; import numpy"], cwd=SCRIPT_DIR)
    if code == 0:
        # log_to(log, "Dependencies verified (skipping reinstall).")
        return True

    log_to(log, "Installing/updating dependencies (this may take a moment)...")
    code, out = run_cmd_capture([str(VENV_PYTHON), "-m", "pip", "install", "--upgrade", "pip"], cwd=SCRIPT_DIR)
    if code != 0:
        log_to(log, f"pip upgrade failed (code {code}):\n{out}")
        return False

    code, out = run_cmd_capture([str(VENV_PYTHON), "-m", "pip", "install", "-r", str(req)], cwd=SCRIPT_DIR)
    if code != 0:
        log_to(log, f"pip install failed (code {code}):\n{out}")
        return False

    return True


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
    """Ensure the starter set of voice models is downloaded from Hugging Face."""
    voices_root = SCRIPT_DIR.parent
    
    all_good = True
    
    for name, info in STARTER_MODELS.items():
        onnx_path = voices_root / info["rel_path"]
        json_path = onnx_path.with_suffix(".onnx.json")
        
        # Ensure directory exists
        onnx_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Download ONNX if missing
        if not onnx_path.exists():
            log_to(log, f"Downloading model: {name}...")
            try:
                log_to(log, f"  Fetching {info['onnx_url']}...")
                
                # Download to a temporary file first to prevent corruption
                temp_path = onnx_path.with_suffix(".tmp")
                urllib.request.urlretrieve(info["onnx_url"], temp_path)
                
                # Rename to final path on success
                if temp_path.exists():
                    temp_path.replace(onnx_path)
                    log_to(log, f"  Saved to {onnx_path.name}")
                else:
                    log_to(log, f"  Error: Temp file not found for {name}")
                    all_good = False
                    
            except Exception as e:
                log_to(log, f"Failed to download {name}: {e}")
                all_good = False
                continue

        # Download JSON if missing
        if not json_path.exists():
            try:
                # JSON files are small, but let's be safe
                temp_json = json_path.with_suffix(".tmp")
                urllib.request.urlretrieve(info["json_url"], temp_json)
                
                if temp_json.exists():
                    temp_json.replace(json_path)
                    log_to(log, f"  Fetched config for {name}")
            except Exception as e:
                log_to(log, f"Failed to download config for {name}: {e}")
                all_good = False
    
    if all_good:
        log_to(log, "All starter models checked/downloaded.")
    
    return all_good


def ensure_piper_binary(log: tk.Text) -> bool:
    """Ensure the Piper binary is present in src/piper/."""
    piper_dir = SCRIPT_DIR / "piper"
    
    # Check for executable
    exe_name = "piper.exe" if os.name == "nt" else "piper"
    
    # Check standard location
    if (piper_dir / exe_name).exists():
        return True
    # Check nested location (common in some archives)
    if (piper_dir / "piper" / exe_name).exists():
        return True

    log_to(log, "Piper binary not found. Downloading...")
    
    # Redirect stdout to capture download progress for the log
    class LogRedirect:
        def __init__(self, text_widget):
            self.text_widget = text_widget
        def write(self, msg):
            if msg.strip():
                # Use after() to be thread-safe with Tkinter
                self.text_widget.after(0, lambda: log_to(self.text_widget, msg.strip()))
        def flush(self):
            pass

    original_stdout = sys.stdout
    try:
        sys.stdout = LogRedirect(log)
        download_piper.download_and_extract_piper(SCRIPT_DIR)
    except Exception as e:
        log_to(log, f"Download failed: {e}")
        return False
    finally:
        sys.stdout = original_stdout

    # Verify again
    if (piper_dir / exe_name).exists() or (piper_dir / "piper" / exe_name).exists():
        log_to(log, "Piper binary installed successfully.")
        return True
    
    log_to(log, "Download finished but binary still missing. Check logs.")
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
    """Find and stop any process listening on the specified port."""
    if os.name != "nt":
        # Linux/Mac implementation using lsof
        if not shutil.which("lsof"):
            log_to(log, "Error: 'lsof' command not found. Cannot stop server automatically.")
            return False

        try:
            # Find PID
            cmd = ["lsof", "-t", "-i", f":{port}"]
            code, out = run_cmd_capture(cmd)
            if code != 0 or not out.strip():
                log_to(log, f"No process listening on port {port}.")
                return True
            
            pids = out.strip().split()
            for pid in pids:
                run_cmd_capture(["kill", "-9", pid])
            
            log_to(log, f"Stopped server on port {port} (PIDs: {', '.join(pids)}).")
            return True
        except Exception as e:
            log_to(log, f"Stop failed: {e}")
            return False

    # Windows implementation using PowerShell
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
        log_to(log, f"Stop failed (code {code}):\n{out}")
        return False
    if out.strip() == "NO_LISTENER":
        log_to(log, f"No process listening on port {port}.")
        return True
    log_to(log, f"Stopped server on port {port}.")
    return True


def start_server_process(log: tk.Text, host: str, port: int) -> bool:
    """Start the Piper TTS server as a background process."""
    if not ensure_venv_and_deps(log):
        return False
    
    # Ensure Piper binary is present
    if not ensure_piper_binary(log):
        log_to(log, "Error: Piper binary missing and download failed.")
        return False

    # Ensure models are actually downloaded (not just LFS pointers)
    if not ensure_starter_models(log):
        log_to(log, "Warning: Could not verify/download voice models. Server may fail to load voices.")

    python_for_server = VENV_PYTHON
    if os.name == "nt" and VENV_PYTHONW.exists():
        # Prefer pythonw.exe on Windows to avoid opening a console window.
        python_for_server = VENV_PYTHONW

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

    log_to(log, f"Starting server: {' '.join(cmd)}")

    # Detached process so closing UI doesn't kill the server (optional).
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "CREATE_NO_WINDOW", 0)

    try:
        subprocess.Popen(
            cmd,
            cwd=str(SCRIPT_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **kwargs,
        )
    except Exception as e:
        log_to(log, f"Failed to start server: {e}")
        return False

    return True


def autostart_install(log: tk.Text) -> bool:
    """
    Install autostart mechanism based on the OS.
    - Windows: Startup folder shortcut
    - Mac: LaunchAgent plist
    - Linux: XDG Desktop Entry
    """
    if os.name == "nt":
        return _autostart_install_windows(log)
    elif sys.platform == "darwin":
        return _autostart_install_mac(log)
    else:
        return _autostart_install_linux(log)

def _autostart_install_windows(log: tk.Text) -> bool:
    bat = SCRIPT_DIR / "tools" / "start_piper_server.bat"
    if not bat.exists():
        log_to(log, "Missing start_piper_server.bat")
        return False

    link_path = _startup_shortcut_path()
    link_path.parent.mkdir(parents=True, exist_ok=True)

    ps = (
        f"$WshShell = New-Object -ComObject WScript.Shell; "
        f"$Shortcut = $WshShell.CreateShortcut({_ps_single_quote(str(link_path))}); "
        f"$Shortcut.TargetPath = {_ps_single_quote(str(bat))}; "
        f"$Shortcut.WorkingDirectory = {_ps_single_quote(str(SCRIPT_DIR))}; "
        f"$Shortcut.WindowStyle = 7; "
        f"$Shortcut.Save(); "
        f"Write-Output 'OK'"
    )

    code, out = powershell(ps)
    if code != 0:
        log_to(log, f"Autostart install failed (code {code}):\n{out}")
        return False

    if not link_path.exists():
        log_to(log, "Autostart install may have failed: shortcut was not created.")
        return False

    # Cleanup legacy Run-key entry (older versions used this); ignore failures.
    run_cmd_capture(["reg", "delete", RUN_KEY, "/v", RUN_VALUE_NAME, "/f"], cwd=SCRIPT_DIR)

    log_to(log, "Enabled autostart (Startup folder shortcut).")
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
    def __init__(self, master: tk.Tk):
        super().__init__(master)
        self.master = master

        self.host_var = tk.StringVar(value=DEFAULT_HOST)
        self.port_var = tk.IntVar(value=DEFAULT_PORT)
        self.voice_var = tk.StringVar()
        self.random_var = tk.BooleanVar(value=True)
        self.auto_restart_var = tk.BooleanVar(value=False)

        self.status_var = tk.StringVar(value="Status: unknown")
        self.autostart_var = tk.StringVar(value="Autostart: unknown")

        self.is_playing = False  # Track if audio is playing
        self.playback_process = None  # Track external player process (Mac/Linux)
        self._loading_active = False  # Track if TTS is generating
        self._should_be_running = False
        self._last_restart_time = 0

        self.available_voices = scan_voices()
        self._load_settings()

        self._status_style = "Badge.Unknown.TLabel"
        self._autostart_style = "Badge.Unknown.TLabel"

        self._build()
        self._refresh_autostart()
        self._schedule_status_refresh()

        # Check for voices in the background at startup
        self._thread(self._initial_setup_check)
        
        # Monitor server logs in background
        self._thread(self._monitor_server_log)

    def _monitor_server_log(self) -> None:
        """Tail the server log file and display new lines in the UI."""
        server_log = SCRIPT_DIR / "piper_server.log"
        
        # Wait for file to exist (loop with checks)
        while True:
            if server_log.exists():
                break
            if not self.master.winfo_exists():
                return
            time.sleep(2)
            
        try:
            with open(server_log, "r", encoding="utf-8") as f:
                # Go to end to start trailing
                f.seek(0, 2)
                while True:
                    if not self.master.winfo_exists():
                        break
                    line = f.readline()
                    if line:
                        msg = line.strip()
                        if msg:
                            # Use after() to update UI thread safely
                            # do not save to file again since it's already in piper_server.log
                            self.master.after(0, lambda m=msg: log_to(self.log, f"[SERVER] {m}", save_to_file=False))
                    else:
                        time.sleep(0.5)
        except Exception:
            pass

    def _initial_setup_check(self) -> None:
        """Run initial setup checks (binary and models) in the background."""
        # Ensure Piper binary is present
        ensure_piper_binary(self.log)
        
        # Ensure starter models are present
        if ensure_starter_models(self.log):
            # If models were downloaded, refresh the UI
            self.master.after(0, self._refresh_voices)

    def _refresh_voices(self) -> None:
        """Rescan voices and update the combobox."""
        self.available_voices = scan_voices()
        if hasattr(self, "voice_combo"):
            self.voice_combo["values"] = [v.name for v in self.available_voices]
            
            # If current selection is empty or invalid, pick the first one
            current = self.voice_var.get()
            if not current or not any(v.name == current for v in self.available_voices):
                if self.available_voices:
                    self.voice_var.set(self.available_voices[0].name)
        
        log_to(self.log, f"Refreshed voices. Found {len(self.available_voices)} voice(s).")

    def _build(self) -> None:
        self.master.title("Piper TTS Server")
        self.grid(row=0, column=0, sticky="nsew")
        self.master.columnconfigure(0, weight=1)
        self.master.rowconfigure(0, weight=1)

        style = ttk.Style()
        # Use native theme on Windows for better-looking checkboxes (standard checkmarks instead of 'X')
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

        # Minimal "badge" styles (foreground only; keeps theme layout intact)
        style.configure("Badge.Running.TLabel", foreground="#22c55e")
        style.configure("Badge.Stopped.TLabel", foreground="#ef4444")
        style.configure("Badge.Error.TLabel", foreground="#f59e0b")
        style.configure("Badge.Unknown.TLabel", foreground="#94a3b8")

        # Voice selection section
        voice_frame = ttk.LabelFrame(self, text="Voice")
        voice_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        voice_frame.columnconfigure(0, weight=1)

        self.voice_combo = ttk.Combobox(voice_frame, textvariable=self.voice_var, state="readonly", width=50)
        self.voice_combo["values"] = [v.name for v in self.available_voices]
        self.voice_combo.grid(row=0, column=0, sticky="ew", padx=8, pady=6)
        self.voice_combo.bind("<<ComboboxSelected>>", lambda e: self._save_voice_selection())
        
        # Test Text section
        test_frame = ttk.Frame(voice_frame)
        test_frame.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))
        test_frame.columnconfigure(1, weight=1)

        ttk.Checkbutton(test_frame, text="Random", variable=self.random_var, command=self._on_random_toggle).grid(row=0, column=0, padx=(0, 8), sticky="n")
        
        self.test_entry = tk.Text(test_frame, height=3, wrap="word", font=("Segoe UI", 9))
        self.test_entry.grid(row=0, column=1, sticky="ew")
        
        test_scroll = ttk.Scrollbar(test_frame, command=self.test_entry.yview)
        test_scroll.grid(row=0, column=2, sticky="ns")
        self.test_entry.configure(yscrollcommand=test_scroll.set)

        # Bindings for Enter and Shift+Enter
        self.test_entry.bind("<Return>", self._on_test_entry_return)
        
        voice_btns = ttk.Frame(voice_frame)
        voice_btns.grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 8))
        
        ttk.Button(voice_btns, text="🔊 Test Voice", command=self._test_clicked).grid(row=0, column=0, padx=(0, 8))
        self.stop_audio_btn = ttk.Button(voice_btns, text="⏹ Stop", command=self._stop_audio_clicked, state="disabled")
        self.stop_audio_btn.grid(row=0, column=1, padx=(0, 8))
        ttk.Button(voice_btns, text="📥 Download", command=self._download_clicked).grid(row=0, column=2, padx=(0, 8))
        ttk.Button(voice_btns, text="📜 How to add voices?", command=self._open_voice_guide).grid(row=0, column=3, padx=(0, 8))

        self.loading_label = ttk.Label(voice_btns, text="", foreground="#3b82f6")
        self.loading_label.grid(row=0, column=4, padx=(8, 0))

        # Initial toggle state
        self._on_random_toggle()

        # Server section
        top = ttk.LabelFrame(self, text="Server")
        top.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="Host").grid(row=0, column=0, sticky="w", padx=8, pady=6)
        ttk.Entry(top, textvariable=self.host_var, width=18).grid(row=0, column=1, sticky="w", padx=8, pady=6)

        ttk.Label(top, text="Port").grid(row=0, column=2, sticky="w", padx=8, pady=6)
        ttk.Entry(top, textvariable=self.port_var, width=8).grid(row=0, column=3, sticky="w", padx=8, pady=6)

        ttk.Checkbutton(top, text="Auto-Restart", variable=self.auto_restart_var, command=self._save_settings).grid(row=0, column=4, sticky="w", padx=8, pady=6)

        btns = ttk.Frame(top)
        btns.grid(row=1, column=0, columnspan=4, sticky="ew", padx=8, pady=(0, 8))

        ttk.Button(btns, text="▶ Start Server", command=self._start_clicked).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(btns, text="⏹ Stop Server", command=self._stop_clicked).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(btns, text="🔍 Check Status", command=self._status_clicked).grid(row=0, column=2, padx=(0, 8))

        self.status_label = ttk.Label(top, textvariable=self.status_var, style=self._status_style)
        self.status_label.grid(row=2, column=0, columnspan=4, sticky="w", padx=8, pady=(0, 8))

        # Training section REMOVED for Server-Only dashboard

        auto_text = "Autostart (Windows)" if os.name == "nt" else "Autostart"
        auto = ttk.LabelFrame(self, text=auto_text)
        auto.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 10))
        auto.columnconfigure(0, weight=1)

        self.autostart_label = ttk.Label(auto, textvariable=self.autostart_var, style=self._autostart_style)
        self.autostart_label.grid(row=0, column=0, sticky="w", padx=8, pady=6)

        auto_btns = ttk.Frame(auto)
        auto_btns.grid(row=1, column=0, sticky="w", padx=8, pady=(0, 8))
        ttk.Button(auto_btns, text="Install", command=self._install_autostart_clicked).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(auto_btns, text="Uninstall", command=self._uninstall_autostart_clicked).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(auto_btns, text="Refresh", command=self._refresh_autostart).grid(row=0, column=2)

        log_frame = ttk.LabelFrame(self, text="Log")
        log_frame.grid(row=4, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self.rowconfigure(4, weight=1)
        self.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)

        self.log = tk.Text(log_frame, height=14, wrap="word", state="disabled")
        self.log.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(log_frame, command=self.log.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=scrollbar.set)

        log_to(self.log, f"Working directory: {SCRIPT_DIR}")
        log_to(self.log, f"Found {len(self.available_voices)} voice(s): {', '.join(v.name for v in self.available_voices)}")

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
        base = self._base_url()
        is_running = False
        try:
            # Increased timeout from default 5s to 10s to avoid false positives when server is busy
            info = http_get_json(f"{base}/health", timeout=10.0)
            if info.get("ok") is True:
                self.status_var.set("Status: running")
                self._status_style = "Badge.Running.TLabel"
                is_running = True
                # If we detect it's running, assume it should be running
                self._should_be_running = True
            else:
                self.status_var.set(f"Status: error ({info.get('error', 'unknown')})")
                self._status_style = "Badge.Error.TLabel"
                # If the server is responding but reporting an error (e.g. stuck), 
                # we should still consider it as "intended to be running" so auto-restart can fix it.
                self._should_be_running = True
        except Exception:
            self.status_var.set("Status: not running")
            self._status_style = "Badge.Stopped.TLabel"

        if hasattr(self, "status_label"):
            self.status_label.configure(style=self._status_style)

        # Auto-restart logic
        if self.auto_restart_var.get() and self._should_be_running and not is_running:
            now = time.time()
            # Check every minute (60s) as requested, with a bit of buffer
            if now - self._last_restart_time > 60:
                log_to(self.log, "Auto-restart: Server not responding, attempting restart...")
                self._last_restart_time = now
                # We don't call _stop_clicked because it might hang if the process is dead but port is bound
                # start_server_process handles cleanup if needed? No, it doesn't.
                # Actually, start_server_process calls ensure_venv_and_deps etc.
                # We should probably call stop_server_by_port first to be sure.
                def restart_work():
                    try:
                        port = int(self.port_var.get() or DEFAULT_PORT)
                        stop_server_by_port(self.log, port)
                        time.sleep(1)
                        self._start_clicked()
                    except Exception as e:
                        log_to(self.log, f"Auto-restart failed: {e}")
                
                self._thread(restart_work)

    def _schedule_status_refresh(self) -> None:
        """Refresh status and schedule the next refresh."""
        self._refresh_status()
        # Refresh every 5 seconds
        self.master.after(5000, self._schedule_status_refresh)

    def _on_random_toggle(self) -> None:
        """Enable or disable the test text entry based on the random checkbox."""
        if self.random_var.get():
            self.test_entry.configure(state="disabled", background="#f0f0f0")
        else:
            self.test_entry.configure(state="normal", background="white")

    def _on_test_entry_return(self, event):
        """Handle Enter key in the test text box."""
        # If Shift is NOT pressed, trigger test and break
        # If Shift IS pressed, do nothing (let default newline happen)
        if not (event.state & 0x0001): 
            self._test_clicked()
            return "break"
        return None

    def _animate_loading(self, step: int = 0) -> None:
        """Animate the loading label with cycling dots."""
        if not self._loading_active:
            self.loading_label.configure(text="")
            return
        
        dots = "." * (step % 4)
        self.loading_label.configure(text=f"Generating{dots}")
        self.master.after(400, lambda: self._animate_loading(step + 1))

    def _start_clicked(self) -> None:
        self._should_be_running = True
        def work():
            self.status_var.set("Status: starting...")
            self._status_style = "Badge.Unknown.TLabel"
            self.master.after(0, lambda: self.status_label.configure(style=self._status_style))

            host = self.host_var.get().strip() or DEFAULT_HOST
            try:
                port = int(self.port_var.get() or DEFAULT_PORT)
            except ValueError:
                log_to(self.log, "Error: Invalid port number.")
                self.master.after(0, self._refresh_status)
                return

            ok = start_server_process(self.log, host, port)
            if ok:
                log_to(self.log, "Start requested. Checking status...")
                # Refresh voices in case they were just downloaded
                self.master.after(0, self._refresh_voices)
                time.sleep(1.2)
                self.master.after(0, self._refresh_status)
            else:
                self.master.after(0, self._refresh_status)

        self._thread(work)

    def _stop_clicked(self) -> None:
        self._should_be_running = False
        self.status_var.set("Status: stopping...")
        self._status_style = "Badge.Unknown.TLabel"
        if hasattr(self, "status_label"):
            self.status_label.configure(style=self._status_style)

        def work():
            try:
                port = int(self.port_var.get() or DEFAULT_PORT)
            except ValueError:
                log_to(self.log, "Error: Invalid port number.")
                return

            stop_server_by_port(self.log, port)
            self.master.after(0, self._refresh_status)

        self._thread(work)

    def _status_clicked(self) -> None:
        self.status_var.set("Status: checking...")
        self._status_style = "Badge.Unknown.TLabel"
        if hasattr(self, "status_label"):
            self.status_label.configure(style=self._status_style)

        def work():
            base = self._base_url()
            try:
                info = http_get_json(f"{base}/health")
                log_to(self.log, f"/health OK:\n{json.dumps(info, indent=2)}")
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", errors="ignore") if hasattr(e, "read") else ""
                log_to(self.log, f"/health HTTP {e.code}:\n{body}")
            except Exception as e:
                log_to(self.log, f"/health failed: {e}")
            self.master.after(0, self._refresh_status)

        self._thread(work)

    def _split_text(self, text: str) -> list[str]:
        """Split text into meaningful chunks (sentences) for smoother TTS playback."""
        # Split by sentence endings (. ! ?) followed by space or newline
        # We use a lookbehind to keep the punctuation with the sentence
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        # Filter out empty strings and further split very long sentences if needed
        chunks = []
        for s in sentences:
            s = s.strip()
            if not s:
                continue
            # If a single "sentence" is still huge (e.g. > 250 chars), split by commas or just length
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
        # Quick check of current status variable
        if "running" not in self.status_var.get().lower():
            log_to(self.log, "Error: Server is not running. Please click 'Start' in the Server section first.")
            # Trigger a status refresh just in case it's actually running now
            self._thread(lambda: self.master.after(0, self._refresh_status))
            return

        def work():
            # Stop any currently playing audio
            if self.is_playing:
                self._stop_audio_clicked()
                time.sleep(0.2)
            
            base = self._base_url()
            url = f"{base}/api/tts"
            
            # Determine text to say
            if self.random_var.get():
                # Fun test messages
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
            chunks = self._split_text(test_msg)
            
            log_to(self.log, f"Testing with voice: {selected_voice or '(default)'}")
            log_to(self.log, f"Text split into {len(chunks)} chunk(s).")
            
            self.is_playing = True
            self.master.after(0, lambda: self.stop_audio_btn.configure(state="normal"))
            
            audio_queue = queue.Queue(maxsize=2) # Buffer up to 2 chunks ahead
            
            def fetcher():
                try:
                    for i, chunk in enumerate(chunks):
                        if not self.is_playing:
                            break
                        
                        payload = {"text": chunk}
                        if selected_voice:
                            payload["voice_model"] = selected_voice
                        
                        # Show loading for the first chunk
                        if i == 0:
                            self._loading_active = True
                            self.master.after(0, self._animate_loading)
                        
                        try:
                            wav_bytes = http_post_json(url, payload)
                            if i == 0:
                                self._loading_active = False
                            audio_queue.put(wav_bytes)
                        except Exception as e:
                            log_to(self.log, f"Chunk {i+1} fetch failed: {e}")
                            if i == 0:
                                self._loading_active = False
                            break
                finally:
                    audio_queue.put(None) # Signal end

            self._thread(fetcher)

            try:
                while self.is_playing:
                    wav_bytes = audio_queue.get()
                    if wav_bytes is None:
                        break
                    
                    # Save to temp file for playback
                    import tempfile
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
                        temp_wav = f.name
                        f.write(wav_bytes)
                    
                    try:
                        # Cross-platform audio playback
                        self.playback_process = audio_playback.play_wav_async(temp_wav)
                        duration = audio_playback.get_wav_duration(temp_wav)
                        
                        # Monitor playback completion
                        start_time = time.time()
                        while time.time() - start_time < duration and self.is_playing:
                            time.sleep(0.1)

                    except Exception as play_err:
                        log_to(self.log, f"Playback failed: {play_err}")
                    finally:
                        # Clean up temp file
                        try:
                            os.remove(temp_wav)
                        except Exception:
                            pass
                
                log_to(self.log, "Audio playback completed.")

            except Exception as e:
                log_to(self.log, f"Playback loop error: {e}")
            finally:
                self.is_playing = False
                self.master.after(0, lambda: self.stop_audio_btn.configure(state="disabled"))

        self._thread(work)

    def _download_clicked(self) -> None:
        # Quick check of current status variable
        if "running" not in self.status_var.get().lower():
            log_to(self.log, "Error: Server is not running. Please click 'Start' in the Server section first.")
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
        """Stop currently playing audio."""
        self.is_playing = False  # Signal any loops to stop
        
        # Cross-platform audio stop
        try:
            audio_playback.stop_playback(self.playback_process)
            self.playback_process = None
        except Exception:
            pass

        self.stop_audio_btn.configure(state="disabled")
        log_to(self.log, "Audio playback stopped.")

    def _install_autostart_clicked(self) -> None:
        def work():
            autostart_install(self.log)
            self.master.after(0, self._refresh_autostart)

        self._thread(work)

    def _uninstall_autostart_clicked(self) -> None:
        def work():
            autostart_uninstall(self.log)
            self.master.after(0, self._refresh_autostart)

        self._thread(work)

    def _load_settings(self) -> None:
        cfg = load_config()
        
        # Load voice
        selected = cfg.get("voice_model", "")
        if selected and any(v.name == selected for v in self.available_voices):
            self.voice_var.set(selected)
        elif self.available_voices:
            self.voice_var.set(self.available_voices[0].name)
            
        # Load auto-restart
        self.auto_restart_var.set(cfg.get("auto_restart", False))

    def _save_settings(self) -> None:
        cfg = load_config()
        cfg["voice_model"] = self.voice_var.get()
        cfg["auto_restart"] = self.auto_restart_var.get()
        save_config(cfg)
        # log_to(self.log, f"Settings saved.")

    def _save_voice_selection(self) -> None:
        self._save_settings()
        log_to(self.log, f"Voice changed to: {self.voice_var.get()}")
        log_to(self.log, "Voice will be used immediately on next TTS request.")

    def _refresh_training_projects(self) -> None:
        """Scan tts_dojo folder for available voice projects."""
        dojo_dir = SCRIPT_DIR.parent / "training" / "make piper voice models" / "tts_dojo"
        projects = []
        if dojo_dir.exists():
            for item in dojo_dir.iterdir():
                if item.is_dir() and item.name.endswith("_dojo"):
                    projects.append(item.name)
        
        self.training_project_combo["values"] = sorted(projects)
        if projects and not self.training_project_var.get():
            self.training_project_var.set(projects[0])
        elif not projects:
            self.training_project_var.set("")

    def _create_new_voice_clicked(self) -> None:
        """Show a prompt to create a new voice project."""
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
        
        training_dir = SCRIPT_DIR.parent / "training" / "make piper voice models"
        script = training_dir / "new_dojo.ps1"
        
        def work():
            log_to(self.log, f"Creating new voice: {voice_name}...")
            code, out = powershell(f"cd '{training_dir}'; ./new_dojo.ps1 {voice_name}")
            if code == 0:
                log_to(self.log, f"Successfully created {voice_name}.")
                self.master.after(0, self._refresh_training_projects)
                self.master.after(0, lambda: self.training_project_var.set(f"{voice_name}_dojo"))
                # Open the dataset folder for them
                self.master.after(0, self._open_dataset_folder_clicked)
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

    def _auto_split_clicked(self) -> None:
        """Prompt for a long audio file and split it into the dataset folder."""
        project = self.training_project_var.get()
        if not project:
            log_to(self.log, "Error: No project selected.")
            return

        file_path = filedialog.askopenfilename(
            title="Select Long Audio File of Patrick",
            filetypes=[("Audio Files", "*.wav *.mp3 *.m4a *.flac"), ("All Files", "*.*")]
        )
        if not file_path:
            return

        dataset_path = SCRIPT_DIR.parent / "training" / "make piper voice models" / "tts_dojo" / project / "dataset"
        split_script = SCRIPT_DIR / "auto_split.py"

        def update_progress(val, text):
            self.master.after(0, lambda: self.progress_var.set(val))
            self.master.after(0, lambda: self.progress_label.configure(text=text))

        def work():
            self.master.after(0, lambda: self.progress_var.set(0))
            self.master.after(0, lambda: self.progress_label.configure(text="Initialising..."))
            
            log_to(self.log, f"Splitting master file for {project}...")
            log_to(self.log, "This will automatically detect silences and create small clips.")
            
            code = run_cmd_realtime([str(VENV_PYTHON), str(split_script), str(file_path), str(dataset_path)], self.log, update_progress)
            
            if code == 0:
                self.master.after(0, lambda: self.progress_var.set(100))
                self.master.after(0, lambda: self.progress_label.configure(text="Done!"))
                log_to(self.log, f"Splitting complete for {project}!")
                # Show a popup to the user
                from tkinter import messagebox
                self.master.after(0, lambda: messagebox.showinfo("Success", f"Audio splitting complete!\n\nFound and created numerous voice clips in the dataset folder."))
                # Open folder so user can see the results
                self.master.after(0, self._open_dataset_folder_clicked)
            else:
                log_to(self.log, f"Splitting failed.")
                self.master.after(0, lambda: self.progress_label.configure(text="Failed"))

        self._thread(work)

    def _auto_transcribe_clicked(self) -> None:
        """Run the auto-transcription script on the dataset folder."""
        project = self.training_project_var.get()
        if not project:
            log_to(self.log, "Error: No project selected.")
            return
            
        dataset_path = SCRIPT_DIR.parent / "training" / "make piper voice models" / "tts_dojo" / project / "dataset"
        transcribe_script = SCRIPT_DIR / "auto_transcribe.py"
        
        def update_progress(val, text):
            self.master.after(0, lambda: self.progress_var.set(val))
            self.master.after(0, lambda: self.progress_label.configure(text=text))

        def work():
            self.master.after(0, lambda: self.progress_var.set(0))
            self.master.after(0, lambda: self.progress_label.configure(text="Loading Model..."))
            
            log_to(self.log, f"Auto-Transcribing recordings for {project}...")
            log_to(self.log, "This uses the 'Whisper' AI model. First time may take a moment to download.")
            
            # Run in the manager's venv
            code = run_cmd_realtime([str(VENV_PYTHON), str(transcribe_script), str(dataset_path)], self.log, update_progress)
            
            if code == 0:
                self.master.after(0, lambda: self.progress_var.set(100))
                self.master.after(0, lambda: self.progress_label.configure(text="Done!"))
                log_to(self.log, f"Transcription complete for {project}!")
                from tkinter import messagebox
                self.master.after(0, lambda: messagebox.showinfo("Success", f"Transcription complete!\n\nThe AI has successfully written the metadata.csv file for {project}."))
            else:
                log_to(self.log, f"Transcription failed.")
                self.master.after(0, lambda: self.progress_label.configure(text="Failed"))

        self._thread(work)

    def _start_training_clicked(self) -> None:
        """Start training for the selected project."""
        project = self.training_project_var.get()
        if not project:
            log_to(self.log, "Error: No project selected to train.")
            return
            
        training_dir = SCRIPT_DIR.parent / "training" / "make piper voice models"
        training_script = training_dir / "run_training.ps1"
        
        log_to(self.log, f"Starting training for {project}...")
        
        try:
            if os.name == "nt":
                # Launch the training script, telling it which project to use
                subprocess.Popen([
                    "powershell.exe", 
                    "-NoProfile",
                    "-ExecutionPolicy", "Bypass", 
                    "-Command", f"cd '{training_dir}'; ./run_training.ps1 -SelectedDojo {project}"
                ], creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                log_to(self.log, "Training is currently only optimized for Windows.")
        except Exception as e:
            log_to(self.log, f"Failed to start training: {e}")

    def _open_voice_guide(self) -> None:
        """Open the voice guide README file."""
        guide_path = SCRIPT_DIR.parent / "voices" / "HOW_TO_ADD_VOICES.md"
        if guide_path.exists():
            import subprocess
            try:
                if os.name == "nt":
                    os.startfile(str(guide_path))
                else:
                    # Non-Windows fallback
                    opener = "open" if sys.platform == "darwin" else "xdg-open"
                    subprocess.Popen([opener, str(guide_path)])
            except Exception as e:
                log_to(self.log, f"Failed to open guide: {e}")
        else:
            log_to(self.log, f"Voice guide not found: {guide_path}")


def main() -> None:
    if not check_single_instance():
        # If we can't bind, another instance is likely running.
        # The launcher (PS1) handles bringing the existing window to front on Windows.
        sys.exit(0)

    root = tk.Tk()
    App(root)
    root.minsize(740, 520)
    root.mainloop()


if __name__ == "__main__":
    main()
