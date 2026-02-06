# PiperTTS Mockingbird 🎤

Welcome! This is a simple text-to-speech server that runs on your computer.

> [!IMPORTANT]
> **⚖️ Legal & Ethical Notice:** This tool is intended for ethical use only. By using PiperTTS Mockingbird, you agree to only clone voices of consenting individuals (including yourself). Please read our [**Ethical Usage Disclaimer**](ETHICAL_USAGE_DISCLAIMER.md) before proceeding.

## Quick Start

- **Windows:** Double-click [`Open PiperTTS Mockingbird (Windows).vbs`](Open%20PiperTTS%20Mockingbird%20(Windows).vbs) to open the control panel.
- **macOS:** Run `chmod +x "Open PiperTTS Mockingbird (macOS).command"` then double-click the file.
- **Linux:** Run `chmod +x "Open PiperTTS Mockingbird (Linux).sh"` then run it from your terminal or file manager.

### Prerequisites
- **Python 3.9+** installed on your system.
- **Docker Desktop** (only required for training custom voices).

**Note:** On the first run, the app will automatically download the Piper engine and a set of starter voices (about 350MB total). This may take a few minutes depending on your internet speed.

## Using the Control Panel

When you open the dashboard, you'll see a simple control panel:

### Voice Section
- **Dropdown menu**: Select which voice you want to use
- **Random Checkbox**: 
  - **Checked**: The voice will say a random fun sentence.
  - **Unchecked**: You can type your own text in the box to hear it spoken.
- **Test Voice**: Click to hear the selected voice (shows a "Generating..." animation while working)
- **Stop**: Stops the current test audio (works on Windows, Mac, and Linux)
- **How to add voices?**: Opens a guide for adding more voices

### Server Section
- **Start**: Click to start the text-to-speech server
- **Stop**: Click to stop the server
- **Check Status**: See if the server is running
- **Host & Port**: These control where the server runs (usually you don't need to change these)

### What the Server Does
The server lets other programs on your computer convert text to speech. Once you click **Start**, any app you've connected to this server can use it.

**Status Colors:**
- 🟢 Green = Running
- 🔴 Red = Stopped

### Autostart
You can make the server start automatically when you turn on your computer:
- **Install**: Enables automatic startup
- **Uninstall**: Disables automatic startup
- **Refresh**: Checks the current status

## Adding More Voices

Click the **"How to add voices?"** button in the control panel, or check the **[`voices/HOW_TO_ADD_VOICES.md`](voices/HOW_TO_ADD_VOICES.md)** file for step-by-step instructions.

All your voice files go in the `voices/` folder.

**Voice Quality Levels:**
Piper voices come in three quality levels:
- **High** - Best sound quality, but uses more computer resources
- **Medium** - Balanced quality and performance (recommended)
- **Low** - Fastest, uses less resources

If the voices are making your computer slow or overheat, consider using medium or low quality voices instead of high quality.

## Connecting Other Apps

Once the server is running, other programs can connect to it at:
```
http://127.0.0.1:5002/api/tts
```

**Quick Example (cURL):**
```bash
curl -X POST http://127.0.0.1:5002/api/tts \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello world", "voice_model": "Ryan"}' \
  --output test.wav
```

**Developer Note:** The server includes automatic security hardening that's completely invisible:
- CORS restricted to localhost development ports
- Input validation on all endpoints
- Optional API key authentication (via `PIPER_API_KEY` env variable)
- See [docs/SECURITY_HARDENING.md](docs/SECURITY_HARDENING.md) for details

## 🔒 Security Note
This tool is built to be **secure for local use** with invisible protections against common web attacks. The latest version includes:
- ✅ Localhost-only CORS (blocks malicious websites)
- ✅ Input sanitization (prevents injection attacks)
- ✅ Optional API key authentication
- ✅ Safe command execution

**For Local Use**: Zero configuration needed - it's secure by default!

**For Internet Exposure**: Not recommended. If you need remote access, use a reverse proxy (nginx, Caddy) with proper authentication and HTTPS.

For technical security details, see [docs/SECURITY_HARDENING.md](docs/SECURITY_HARDENING.md).

## System Requirements

### 🎤 Just Want to Use TTS with Existing Voices?
**Runs on a potato!** 🥔 The Piper TTS engine is extremely lightweight.

- **CPU**: 1-2 cores (even old/budget CPUs work)
- **RAM**: 2GB minimum, 4GB recommended
- **Storage**: ~500 MB + 50-100 MB per voice
- **OS**: Windows, Linux, or macOS with Python
- **GPU**: Not needed

✔ Works great on Raspberry Pi 4, budget laptops, old desktops, and even low-end systems!

### 🏋️ Want to Train Custom Voices?
**That's where you need proper hardware.** Voice training is computationally intensive.

#### Minimum (CPU-only training - very slow)
- **CPU**: 6+ cores (4+ cores will work but slower)
- **RAM**: 16GB minimum
- **Storage**: 10GB+ free space (SSD strongly recommended)
- **OS**: Windows with Docker Desktop (WSL2)
- **GPU**: Not required but highly recommended
- **Training Time**: 12-24 hours per voice

#### Recommended (GPU-accelerated training)
- **CPU**: 6+ cores
- **RAM**: 16GB+ (32GB ideal)
- **GPU**: NVIDIA GPU with 8GB+ VRAM (GTX 1070 Ti or better)
- **Storage**: SSD with 20GB+ free space
- **OS**: Windows with Docker Desktop (WSL2 enabled)
- **Training Time**: 2-4 hours per voice

#### Optimal (Fast training)
- **CPU**: 8+ cores
- **RAM**: 32GB+
- **GPU**: NVIDIA GPU with 12GB+ VRAM (RTX 3060, RTX 3080, etc.)
- **Storage**: SSD with 50GB+ free space
- **OS**: Windows with Docker Desktop (WSL2 enabled)
- **Training Time**: 1-3 hours per voice

**Note:** The TTS server itself requires minimal resources. Higher specifications are only needed for the Docker-based voice training pipeline.

## Troubleshooting

**Server won't start?**
- Make sure you have Python installed on your computer
- Check the log section at the bottom of the control panel for error messages

**No voices in dropdown?**
- The app automatically downloads starter voices on first run. Make sure you have an internet connection.
- If they didn't download, check the log section at the bottom for errors.
- You can also manually add voices to the `voices/` folder. Each voice needs two files: `.onnx` and `.onnx.json`.

**Voice test doesn't work?**
- Make sure the server is started (Status should be green)
- Check that the voice files are complete

## For Developers

### Installing Dependencies

**For maximum stability** (recommended for production):
```bash
pip install -r src/requirements-frozen.txt
```
This installs exact versions that are tested and guaranteed to work together.

**For development** (if you want to try newer versions):
```bash
pip install -r src/requirements.txt
```
This installs the latest compatible versions of each package.

### Long-Term Stability

This project is designed to be "set and forget":
- The training environment uses Docker with pinned versions, so it will work identically years from now
- The frozen requirements file ensures the server dependencies never break
- All paths are relative, so you can move the project folder anywhere
- No external APIs or cloud dependencies (except optional voice downloads)

## Roadmap & Future Vision

- **High-Fidelity "Turbo" Mode**: One day I might add **Kokoro-82M** to this UI for users who want the absolute highest quality vocal prosody.
- **Project Philosophy**: I originally chose **Piper** because it is the fastest local TTS engine available and can run on almost any hardware—even "potatoes" like a Raspberry Pi 4. Speed and accessibility are currently the top priorities.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---


Need more help? Check the logs at the bottom of the control panel - they'll tell you what's happening!
