# Installation & Testing Guide for Home Assistant Integration

## Installation

### 1. Install Wyoming Library

```bash
# Navigate to your project directory
cd "C:/path/to/piper_tts_server"

# Install Wyoming library
pip install wyoming==1.8.0
```

Or install all dependencies at once:
```bash
pip install -r src/requirements.txt
```

### 2. Verify Installation

```bash
python -c "import wyoming; print('Wyoming installed successfully!')"
```

Expected output: `Wyoming installed successfully!`

## Testing the Features

### Test 1: Home Assistant Export

1. **Start the server:**
   ```bash
   python src/piper_server.py
   ```

2. **Open the dashboard:**
   - Navigate to http://localhost:5002
   - Go to **Settings** tab
   - Scroll to **Home Assistant Integration** section

3. **Test export:**
   - Click **Refresh Voice List**
   - You should see all voices from `voices/` directory
   - Click **Export for HA** on any voice
   - A ZIP file should download automatically

4. **Verify export:**
   - Check `exports/home_assistant/` folder
   - You should find `{voice_name}_home_assistant.zip` files

### Test 2: Wyoming Protocol Server

1. **Start Wyoming server via UI:**
   - In the dashboard, go to Settings tab
   - Find **Wyoming Protocol Server** section
   - Click **Start Server**
   - Status should change to "Running" with a green dot

2. **Verify server is listening:**
   ```powershell
   # Check if port 10200 is open
   Test-NetConnection -ComputerName localhost -Port 10200
   ```

3. **Test standalone mode:**
   ```bash
   python src/wyoming_server.py --voices-dir voices --piper-exe src/piper/piper.exe
   ```
   
   Expected output:
   ```
   INFO Starting Wyoming server on 0.0.0.0:10200
   INFO Loaded X voices for Wyoming protocol
   ```

4. **Stop the server:**
   - Click **Stop Server** in the UI
   - Status should change to "Stopped"

## API Testing (Optional)

### Using PowerShell

```powershell
# List exportable voices
Invoke-RestMethod -Uri "http://localhost:5002/api/ha/list_voices" | ConvertTo-Json -Depth 5

# Export a voice (replace "Ryan" with your voice name)
Invoke-RestMethod -Uri "http://localhost:5002/api/ha/export/Ryan" -Method POST | ConvertTo-Json

# Check Wyoming status
Invoke-RestMethod -Uri "http://localhost:5002/api/wyoming/status" | ConvertTo-Json

# Start Wyoming server
Invoke-RestMethod -Uri "http://localhost:5002/api/wyoming/start" -Method POST | ConvertTo-Json

# Stop Wyoming server
Invoke-RestMethod -Uri "http://localhost:5002/api/wyoming/stop" -Method POST | ConvertTo-Json
```

### Using curl (if installed)

```bash
# List voices
curl http://localhost:5002/api/ha/list_voices

# Export voice
curl -X POST http://localhost:5002/api/ha/export/Ryan

# Wyoming status
curl http://localhost:5002/api/wyoming/status

# Start Wyoming
curl -X POST "http://localhost:5002/api/wyoming/start?host=0.0.0.0&port=10200"

# Stop Wyoming
curl -X POST http://localhost:5002/api/wyoming/stop
```

## Integration with Home Assistant

### Method 1: Export & Manual Install

1. **Export voice from Mockingbird:**
   - Use the dashboard to export your chosen voice
   - Download the ZIP file

2. **Install in Home Assistant:**
   - Extract the ZIP file
   - Copy `.onnx` and `.onnx.json` to your HA Piper directory
   - Restart Home Assistant
   - Go to Settings → Voice Assistants → Piper
   - Your voice should appear in the list

### Method 2: Wyoming Auto-Discovery

1. **Start Wyoming server in Mockingbird:**
   - Open dashboard → Settings → Wyoming section
   - Click "Start Server"
   - Note your computer's IP address (e.g., `192.168.1.100`)

2. **Add integration in Home Assistant:**
   - Go to Settings → Devices & Services
   - Click "Add Integration"
   - Search for "Wyoming Protocol"
   - Enter:
     - Host: `192.168.1.100` (your PC's IP)
     - Port: `10200`
   - Click Submit

3. **Verify:**
   - Your Mockingbird voices should appear automatically
   - Go to Settings → Voice Assistants
   - Select Wyoming TTS
   - Your custom voices should be in the dropdown

## Troubleshooting

### Wyoming Import Errors

**Problem:** `ModuleNotFoundError: No module named 'wyoming'`

**Solution:**
```bash
pip install wyoming==1.8.0
```

### Server Won't Start

**Problem:** Port 10200 already in use

**Solution:**
```powershell
# Find what's using the port
Get-NetTCPConnection -LocalPort 10200

# Or use a different port in the UI
```

**Problem:** "Piper executable not found"

**Solution:**
- Ensure `src/piper/piper.exe` exists
- If not, download Piper from releases page

### Home Assistant Can't Connect

**Problem:** Wyoming server running but HA can't connect

**Solution:**
1. **Check firewall:**
   ```powershell
   # Allow inbound on port 10200
   New-NetFirewallRule -DisplayName "Mockingbird Wyoming" -Direction Inbound -LocalPort 10200 -Protocol TCP -Action Allow
   ```

2. **Verify IP address:**
   ```powershell
   # Get your local IP
   Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.InterfaceAlias -notlike "*Loopback*"}
   ```

3. **Test connectivity from HA:**
   - SSH into Home Assistant
   - Run: `nc -zv YOUR_PC_IP 10200`

### Export Not Downloading

**Problem:** Export succeeds but file doesn't download

**Solution:**
- Check `exports/home_assistant/` folder manually
- Files are saved there even if browser download fails
- Check browser console for JavaScript errors

## Verification Checklist

- [ ] Wyoming library installed (`pip show wyoming`)
- [ ] Main server starts without errors
- [ ] Dashboard opens at http://localhost:5002
- [ ] HA Integration section visible in Settings tab
- [ ] Voice list loads successfully
- [ ] Export creates ZIP file in `exports/home_assistant/`
- [ ] Wyoming server starts via UI
- [ ] Wyoming status shows "Running" with green dot
- [ ] API endpoints respond correctly
- [ ] Wyoming server stops cleanly

## Next Steps

Once everything is working:

1. **Train your first custom voice** using the Voice Studio
2. **Export it for HA** using the new feature
3. **Install in Home Assistant** and test
4. **Optionally enable Wyoming** for auto-discovery
5. **Share your custom voices** with the community!

## Support

If you encounter issues:
1. Check the `logs/` directory for error messages
2. Look at the browser console (F12) for UI errors
3. Verify all prerequisites are installed
4. Review the main documentation in `docs/HOME_ASSISTANT_INTEGRATION.md`
