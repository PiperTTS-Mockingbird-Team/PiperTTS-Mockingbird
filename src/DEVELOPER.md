# PiperTTS Mockingbird 🛠️ Developer & Technical Guide

This document is intended for developers, power users, and anyone looking to integrate PiperTTS Mockingbird into their own projects or modify the codebase.

> **Note on Git LFS:** This repository **does not** use Git LFS for models. Models are downloaded at runtime and are ignored by Git to keep the repository lightweight.

---

## 🏗️ Architecture & Integration

Mockingbird is a **FastAPI** wrapper around the **Piper** TTS engine. It handles process management, text chunking, and provides a RESTful API for synthesis.

### API Endpoint
The server runs by default on port `5002`.

- **URL:** `http://127.0.0.1:5002/api/tts`
- **Method:** `POST`
- **Headers:** `Content-Type: application/json`
- **Body:**
  ```json
  {
    "text": "Hello world",
    "voice_model": "en_US-hfc_female-medium",
    "speed": 1.0
  }
  ```

**Example (cURL):**
```bash
curl -X POST http://127.0.0.1:5002/api/tts \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello world", "voice_model": "Ryan"}' \
  --output test.wav
```

---

## 🔒 Security Hardening

The server is designed for local-first security:
- **CORS Policy:** Restricted to `localhost` and common development ports (8123, 3000, 5173).
- **Input Sanitization:** All text inputs are sanitized to prevent shell injection during Piper execution.
- **Credential Management:** Optional API key authentication can be enabled via the `PIPER_API_KEY` environment variable.
- **Local Isolation:** By default, it binds to `127.0.0.1` to prevent exposure to the local network.

---

## 🛠️ Development Setup

The **One-Click Launchers** at the root of the project are designed to be zero-config for the end user. They automatically handle:
- **Python Environment**: Finding or setting up Python and creating a virtual environment.
- **Dependencies**: Installing all required Python packages (`pip install`).
- **Binaries**: Downloading the appropriate Piper engine for the local OS.
- **Docker**: While Docker is required for training, the scripts handle the container communication so the user doesn't need to manually configure Docker settings.

Manual setup is only required if you want to customize the environment or contribute to the code.

### 1. Manual Installation
From the root directory:
```bash
# Create a virtual environment
python -m venv .venv

# Activate it
# Windows: .venv\Scripts\activate
# Mac/Linux: source .venv/bin/activate

# Install dependencies for development
pip install -r src/requirements.txt

# OR install frozen versions for production stability
pip install -r src/requirements-frozen.txt
```

### 2. Manual Server Control
You can start or stop the server using convenience scripts or terminal commands:

**Convenience Scripts:**
- **Windows:** `tools/start_piper_server.bat` / `tools/stop_piper_server.bat`
- **Linux/Mac:** `src/tools/start.sh`

**Terminal Command:**
```bash
# From the src folder
python -m uvicorn piper_server:app --host 127.0.0.1 --port 5002
```

### 3. Log Locations
If you encounter issues, these files (located in the `src` folder) are the best place to start debugging:
- `piper_manager_ui.log`: Main Dashboard logs.
- `piper_server.log`: FastAPI server output.
- `open_manager_ui.log`: Launcher script debug info.

---

## 🏋️ Voice Training Pipeline

Voice training is handled via a **Docker-based workflow** located in the `training/` folder. This ensures the complex dependencies (CUDA, C++ build tools) remain isolated.

> **Note:** The training backend is a fork and adaptation of the excellent [TextyMcSpeechy](https://github.com/domesticatedviking/TextyMcSpeechy) project.

### Hardware Requirements for Training
Training is computationally expensive and requires significant resources compared to the TTS server.

| Requirement | Minimum (CPU) | Recommended (GPU) | Optimal (High-End) |
| :--- | :--- | :--- | :--- |
| **GPU** | Not required | NVIDIA 8GB+ VRAM | NVIDIA 12GB+ VRAM |
| **RAM** | 16GB | 16GB - 32GB | 32GB+ |
| **Storage** | 10GB+ SSD | 20GB+ SSD | 50GB+ NVMe |
| **Time** | 12-24 hours | 2-4 hours | 1-2 hours |

---

## 📂 Project Structure

```text
piper_tts_server/
├── src/                # FastAPI application & UI
│   ├── piper/          # OS-specific Piper binaries
│   ├── web/            # Dashboard frontend assets
│   └── piper_server.py # Core logic
├── voices/             # .onnx and .onnx.json models
├── training/           # Docker training configs
├── integrations/       # Browser extensions & Add-ons
└── tools/              # Utility scripts
```

- `src/`: Main Python application code.
  - `piper_server.py`: The FastAPI application.
  - `training_manager.py`: Logic for managing Docker training jobs.
  - `piper/`: Dedicated folder for OS-specific Piper binaries.
- `voices/`: Local storage for `.onnx` and `.onnx.json` voice models.
- `training/`: Shell scripts and Docker configurations for the voice dojo.
- `tools/`: Maintenance and helper scripts (metadata fixers, etc).

---

## 📜 Long-Term Stability Goals

- **Zero Cloud:** The project should remain 100% functional without an internet connection (post-setup).
- **Portable:** Uses relative paths wherever possible to ensure the folder can be moved.
- **Pinned Versions:** `requirements-frozen.txt` and Docker images use specific hashes to prevent "bit rot."

---
*For high-level usage instructions, see the [Main README](../README.md).*
