# PiperTTS Mockingbird Local Server

This folder runs a small FastAPI server that lets applications call **Piper** (the native TTS engine) on your machine.

> **Note:** This server implementation and its helper scripts support **Windows, macOS, and Linux**.

## Quick Start (One Click)

**👉 Windows:** Double-click [`Open PiperTTS Mockingbird (Windows).vbs`](../Open%20PiperTTS%20Mockingbird%20(Windows).vbs) at the top level.  
**👉 macOS:** Double-click [`Open PiperTTS Mockingbird (macOS).command`](../Open%20PiperTTS%20Mockingbird%20(macOS).command) (requires `chmod +x` first time).  
**👉 Linux:** Double-click [`Open PiperTTS Mockingbird (Linux).sh`](../Open%20PiperTTS%20Mockingbird%20(Linux).sh) in your file manager (requires `chmod +x` first time).

This opens the **PiperTTS Mockingbird Dashboard** (a window with Start/Stop/Status buttons).

- First launch: automatically creates a Python virtual environment, installs dependencies, downloads the Piper binary, and fetches a starter set of voice models from Hugging Face.
- If something goes wrong, check [`open_manager_ui.log`](open_manager_ui.log) and [`piper_manager_ui.log`](piper_manager_ui.log) for details.

## Automatic Setup

The **PiperTTS Mockingbird Dashboard** handles several setup tasks automatically:
1. **Virtual Environment**: Creates `.venv` and installs `fastapi`, `uvicorn`, etc.
2. **Piper Binary**: Downloads the appropriate Piper executable for your OS into `src/piper/` using `download_piper.py`.
3. **Starter Voices**: Downloads 4 high-quality starter voices (Ryan, Cori, Male, Female) from Hugging Face into the `voices/` folder.

> **Note on Git LFS:** This repository **does not** use Git LFS for models. Models are downloaded at runtime and are ignored by Git to keep the repository lightweight.

## Folder Layout

Expected layout:

- `piper_tts_server/src/piper_server.py`
- `piper_tts_server/src/piper/piper.exe` (Windows) or `piper` (Unix)
- `piper_tts_server/voices/**/**/*.onnx` (voice models)

Example:

```text
piper_tts_server/
├── src/
│   ├── piper/
│   │   ├── piper.exe (or piper)
│   │   └── ...
│   └── piper_server.py
├── voices/
│   └── female/
│       ├── en_US-hfc_female-medium.onnx
│       └── en_US-hfc_female-medium.onnx.json
└── README.md
```

## Install

From the `src` folder:

```bash
python -m pip install fastapi uvicorn pydantic
```

Or (recommended), just use the one-click starters (they create a venv and install deps automatically).

## Start

From the `src` folder:

```bash
python -m uvicorn piper_server:app --host 127.0.0.1 --port 5002
```

### One-click start

- **Windows:** Double-click [`tools/start_piper_server.bat`](tools/start_piper_server.bat)
- **Mac/Linux:** Run `bash src/tools/start.sh` from the root folder.

It will:
- Create a local virtualenv in `.venv/` (first run only)
- Install dependencies from `requirements.txt`
- Start the server on `http://127.0.0.1:5002`

### Stop

- **Windows:** Double-click [`tools/stop_piper_server.bat`](tools/stop_piper_server.bat)
- **Mac/Linux:** The server can be stopped via the Manager UI or by killing the process.

### Auto-start on login (optional)

You can auto-start the server when you log in:

- **Windows:** Use the "Install" button in the Manager UI (creates a Startup shortcut).
- **macOS:** Use the "Install" button in the Manager UI (creates a LaunchAgent).
- **Linux:** Use the "Install" button in the Manager UI (creates an XDG Desktop entry).

## Manager UI

If you want a simple UI with buttons (Start/Stop/Status/Test + Autostart install/uninstall):

- **Windows:** Double-click [`Open PiperTTS Mockingbird (Windows).vbs`](../Open%20PiperTTS%20Mockingbird%20(Windows).vbs) for a silent launch.
- **Mac/Linux:** Run `bash src/tools/dashboard.sh`.

### UI Features
- **Automatic Setup**: Downloads Piper engine and starter voices on first run.
- **Voice Selection**: Dropdown list of all available ONNX models.
- **Test Voice**: 
  - **Random Mode**: Plays a random pre-defined sentence.
  - **Custom Mode**: Allows users to type custom text to synthesize.
  - **Cross-Platform Playback**: Uses `winsound` (Windows), `afplay` (macOS), or `aplay`/`paplay` (Linux).
  - **Loading Animation**: Visual feedback ("Generating...") during synthesis.
- **Server Control**: Start/Stop/Status monitoring with auto-refresh.
- **Autostart Management**: One-click install/uninstall of OS-specific startup entries.
- **Logs**: Integrated log viewer for troubleshooting.

## Key Features

- **In-Memory WAV Generation**: Audio is synthesized and converted to WAV in-memory using `io.BytesIO` and the `wave` module. No temporary files are written to disk.
- **Security**: Hardened against path traversal attacks. The server validates that all voice model requests stay within the `voices/` or `src/` directories.
- **Model Caching**: Available voice models are cached for 60 seconds to improve performance and responsiveness.
- **Cross-Platform**: Full support for Windows, macOS, and Linux.
- **License**: MIT Licensed (with respect to the original Piper MIT release).

## Cross-Platform Support Details

This server is designed to be fully cross-platform, handling OS-specific requirements automatically:

### 💻 Windows
- **Full Support**: Includes the management UI, the TTS server, and automatic startup.
- **Audio Playback**: The "Test Voice" button in the UI plays audio directly through your speakers using `winsound`.
- **Autostart**: Creates a shortcut in the user's `Startup` folder.

### 🍎 macOS
- **Architecture Detection**: Automatically detects Intel or Apple Silicon (M1/M2/M3) and downloads the correct Piper binary.
- **Autostart**: Uses a `LaunchAgent` (plist file) to start the server on login.
- **Audio Playback**: UI playback is currently disabled; the server generates the WAV for external use.

### 🐧 Linux
- **Broad Compatibility**: Works on standard distributions and ARM devices like the **Raspberry Pi**.
- **Architecture Support**: Supports x86_64, aarch64, and armv7l.
- **Autostart**: Uses the standard `XDG Autostart` (.desktop file) system.

## What's What

- **[`Open PiperTTS Mockingbird (Windows).vbs`](../Open%20PiperTTS%20Mockingbird%20(Windows).vbs)** ← **Windows Launcher.** Opens the Manager UI with zero terminal flash.
- **[`piper_manager_ui.py`](piper_manager_ui.py)** — The UI window (Tkinter app).
- **[`piper_server.py`](piper_server.py)** — The FastAPI server that handles TTS requests.
- **[`requirements.txt`](requirements.txt)** — Python dependencies.
- **[`tools/`](tools/)** — Helper scripts for all platforms.
  - **`dashboard.sh`** — Mac/Linux Launcher.
  - **`start.sh`** — Mac/Linux server starter (no UI).
  - **`verify_paths.py`** — Diagnostic tool to check folder structure.
- **`piper/`** — Contains the Piper binary.
- **`voices/`** — Voice models (`.onnx` files).

## Using the API from Other Apps

Any application can connect to the PiperTTS Mockingbird Local Server through its REST API.

### Basic Usage

**Python example:**
```python
import requests

# Convert text to speech
response = requests.post(
    "http://127.0.0.1:5002/api/tts",
    json={"text": "Hello world"}
)

# Get the audio (WAV format)
audio_bytes = response.content

# Save to file or play it
with open("output.wav", "wb") as f:
    f.write(audio_bytes)
```

**Use a specific voice:**
```python
response = requests.post(
    "http://127.0.0.1:5002/api/tts",
    json={
        "text": "Hello world",
        "voice_model": "en_US-hfc_male-medium.onnx"
    }
)
```

**JavaScript/Web example:**
```javascript
fetch('http://127.0.0.1:5002/api/tts', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
        text: 'Hello world',
        voice_model: 'en_US-hfc_female-medium.onnx'
    })
})
.then(r => r.blob())
.then(audio => {
    // Play the audio
    const url = URL.createObjectURL(audio);
    new Audio(url).play();
});
```

### API Endpoints

- **`POST /api/tts`** - Convert text to speech
  - Body: `{"text": "string", "voice_model": "optional-voice-name.onnx"}`
  - Returns: WAV audio file

- **`GET /health`** - Check server status
  - Returns: `{"ok": true, "model": "path/to/current/voice.onnx", ...}`

### Network Access

To allow other devices on your network to connect:

1. In the manager UI, change **Host** from `127.0.0.1` to `0.0.0.0`
2. Click **Stop** then **Start**
3. Other devices can connect using your computer's IP address:
   - Example: `http://192.168.1.100:5002/api/tts`

### CORS Support

The server has CORS enabled by default, so web applications can call it directly from the browser.

---

## System Requirements

### Minimum Specs
Enough to run Piper and generate speech with short clips or low-quality voices:
- **CPU**: 1 core (basic)
- **RAM**: ~1 GB minimum
- **Storage**: ~500 MB base + 50-100 MB per voice model
- **OS**: Windows, Linux, or macOS with Python support
- **GPU**: Optional (not required)

✔ Can run on Raspberry Pi 4-class hardware and small servers.

### Recommended Specs
For smooth real-time performance with medium/high-quality voices:
- **CPU**: 4+ cores with good single-thread performance (fast clock speed)
- **RAM**: 4 GB or more
- **Storage**: SSD for faster model loading
- **OS**: Same as minimum

This setup handles longer text smoothly with lower latency.

### GPU Acceleration (Optional)
Piper supports GPU acceleration via ONNX Runtime with CUDA, but:
- **Performance is mixed** — many users find CPUs faster unless GPU + runtime is properly configured
- If using GPU, even a mid-range card (NVIDIA GTX/RTX) can help with high-quality voices or bulk generation
- GPU support is available but **not required** unless doing large-scale or extremely fast synthesis

**Quick Summary:**
- **Minimum**: Low-power CPU, 1 GB RAM, ~500 MB+ storage
- **Recommended**: 4+ cores CPU, 4 GB+ RAM, SSD
- **Optional**: GPU with ONNX Runtime GPU support (NVIDIA + CUDA)

---

Health check endpoint: http://127.0.0.1:5002/health

## Extension Settings

In the extension settings:

- **TTS Provider**: `Piper (Local Server)`
- **Piper Endpoint**: `http://127.0.0.1:5002/api/tts`
