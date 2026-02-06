# Home Assistant & Wyoming Integration

## Overview

This integration adds two powerful features to PiperTTS Mockingbird:

1. **Export to Home Assistant** - Package trained voices for easy installation in Home Assistant
2. **Wyoming Protocol Server** - Enable direct voice access from Home Assistant without manual file copying

## 🚀 Quick Start

### Prerequisites

Install the Wyoming library:
```bash
pip install wyoming==1.8.0
```

Or install all dependencies:
```bash
pip install -r src/requirements.txt
```

## 📦 Export to Home Assistant

### What it does
Packages your trained `.onnx` and `.onnx.json` voice files into a ready-to-use ZIP file with installation instructions.

### How to use

1. **Via Web UI:**
   - Open the PiperTTS Mockingbird Dashboard
   - Go to **Settings** tab
   - Scroll to **Home Assistant Integration** section
   - Click **Refresh Voice List** to see available voices
   - Click **Export for HA** next to any voice
   - The ZIP file will download automatically

2. **Via API:**
   ```bash
   # List exportable voices
   curl http://localhost:5002/api/ha/list_voices
   
   # Export a specific voice
   curl -X POST http://localhost:5002/api/ha/export/MyVoice
   
   # Download the exported package
   curl http://localhost:5002/api/ha/download/MyVoice -o MyVoice_ha.zip
   ```

### Installation in Home Assistant

1. Extract the downloaded ZIP file
2. Copy both `.onnx` and `.onnx.json` files to:
   - **Docker**: `/data/piper/voices/`
   - **Home Assistant OS**: `/config/piper/voices/`
   - **Supervised**: `/usr/share/hassio/homeassistant/piper/voices/`
3. Go to: Settings → Voice Assistants → Piper → Add Language
4. Your custom voice will appear in the dropdown
5. Select and click "Add"

## 🌐 Wyoming Protocol Server

### What it does
Enables Home Assistant to **automatically discover** your Mockingbird voices over the network without manual file copying. Your trained voices become instantly available in Home Assistant.

### How to use

1. **Via Web UI:**
   - Open the PiperTTS Mockingbird Dashboard
   - Go to **Settings** tab
   - Find **Wyoming Protocol Server** section
   - Configure host (default: `0.0.0.0`) and port (default: `10200`)
   - Click **Start Server**
   - Copy the connection info for Home Assistant

2. **Via API:**
   ```bash
   # Start Wyoming server
   curl -X POST "http://localhost:5002/api/wyoming/start?host=0.0.0.0&port=10200"
   
   # Check status
   curl http://localhost:5002/api/wyoming/status
   
   # Stop server
   curl -X POST http://localhost:5002/api/wyoming/stop
   ```

3. **Standalone Mode:**
   ```bash
   # Run Wyoming server directly
   python src/wyoming_server.py --voices-dir voices --piper-exe src/piper/piper.exe
   ```

### Configuration in Home Assistant

1. Make sure Wyoming server is running in Mockingbird
2. In Home Assistant, go to: **Settings** → **Devices & Services**
3. Click **Add Integration**
4. Search for **Wyoming Protocol**
5. Enter your server details:
   - **Host**: Your computer's IP address (e.g., `192.168.1.100`)
   - **Port**: `10200` (or your custom port)
6. Your Mockingbird voices will auto-discover and appear in Voice Assistants

## 🔧 Technical Details

### File Structure

```
src/
├── ha_export.py           # Voice export logic
├── wyoming_server.py      # Wyoming protocol server
├── piper_server.py        # Updated with HA/Wyoming endpoints
└── web/
    ├── ha_integration.js  # UI controls for HA features
    ├── ha_integration.css # Styling for HA UI
    └── index.html         # Updated to include HA module
```

### API Endpoints

#### Home Assistant Export
- `GET /api/ha/list_voices` - List exportable voices
- `POST /api/ha/export/{voice_name}` - Export a voice
- `GET /api/ha/download/{voice_name}` - Download exported package
- `GET /api/ha/stats` - Get export statistics

#### Wyoming Server
- `POST /api/wyoming/start` - Start Wyoming server
- `POST /api/wyoming/stop` - Stop Wyoming server
- `GET /api/wyoming/status` - Get server status

### Wyoming Protocol

Wyoming is an open standard from the [Open Home Foundation](https://www.openhomefoundation.org/) that enables voice assistants to communicate with TTS/STT services.

**Key Features:**
- Lightweight JSON-based protocol
- Raw PCM audio streaming
- Auto-discovery in Home Assistant
- Multi-voice support

**Standard Port:** 10200 (configurable)

## 🎯 Use Cases

### Export Method (Manual)
Best for:
- One-time voice installations
- Sharing voices with others
- Offline Home Assistant installations
- Backup and archival

### Wyoming Method (Automatic)
Best for:
- Frequent voice updates during training
- Multiple Home Assistant instances
- Real-time voice testing
- Development workflows

## 🐛 Troubleshooting

### Wyoming Server Won't Start

**Error:** "Piper executable not found"
- **Solution:** Make sure Piper is installed in `src/piper/` directory

**Error:** "Wyoming library not installed"
- **Solution:** Run `pip install wyoming==1.8.0`

**Error:** "Port already in use"
- **Solution:** Change the port in Settings or stop the conflicting service

### Home Assistant Can't Find Voices

1. **Check Wyoming server status** in PiperTTS Mockingbird Dashboard
2. **Verify network connectivity** - ping your PC from Home Assistant
3. **Check firewall** - allow port 10200 through your firewall
4. **Restart Home Assistant** integration after starting Wyoming server

### Export Download Not Working

- Check that the voice has `.onnx` and `.onnx.json` files in `voices/` directory
- Look in `exports/home_assistant/` for exported files
- Check browser console for errors

## 📚 Additional Resources

- [Home Assistant Piper Integration](https://www.home-assistant.io/integrations/piper/)
- [Wyoming Protocol Specification](https://github.com/rhasspy/wyoming)
- [Piper TTS Documentation](https://github.com/rhasspy/piper)

## 🤝 Contributing

This integration was designed to be modular and extensible. The code is well-documented with:
- Type hints
- Comprehensive docstrings
- Error handling
- Logging

Feel free to extend the functionality or submit improvements!

## 📄 License

MIT License - Same as the main Mockingbird project
Copyright (c) 2026 PiperTTS Mockingbird Developers
