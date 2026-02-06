# Installation & Testing Guide

## Quick Start

### 1. Start Your Mockingbird Server
Before loading the extension, make sure your Mockingbird TTS server is running:
```bash
cd src
python piper_server.py
```
The server should be running on `http://localhost:5002`

### 2. Load Extension in Chrome

1. Open Chrome and go to: `chrome://extensions/`
2. Toggle on "Developer mode" (top-right corner)
3. Click "Load unpacked"
4. Navigate to and select: `piper_tts_server/integrations/mockingbird_extension/`
5. The extension should appear with a bird icon

### 3. Test the Extension

**Test 1: Check Connection**
1. Click the extension icon
2. Side panel opens
3. Should show "Server connected" with green dot
4. Should show your available voices in dropdown

**Test 2: Read Selected Text**
1. Go to any webpage (e.g., Wikipedia article)
2. Highlight some text
3. Click the floating "🔊 Read" button that appears
4. Audio should start playing
5. Text should be highlighted as it reads

**Test 3: Read Full Page**
1. Go to any article page
2. Click the extension icon to open side panel
3. Click "Read Page" button
4. Should read the main content

**Test 4: Keyboard Shortcuts**
1. Select some text
2. Press `Alt+A` - should start reading
3. Press `Alt+A` again - should pause
4. Press `Alt+S` - should stop

## Known Issues to Watch For

### If "Server offline" shows:
- Make sure Mockingbird server is running on port 5002
- Check `http://localhost:5002/health` in browser
- Look at Advanced Settings → Test Connection

### If no voices appear:
- Make sure you have `.onnx` voice files in `voices/` folder
- Restart the Mockingbird server
- Check server console for errors

### If reading doesn't start:
- Check browser console (F12) for errors
- Reload the webpage
- Try reloading the extension

### If highlighting doesn't work:
- This is expected on some complex websites
- Audio should still play correctly
- Try on a simple article site first

## Customization

### Change Voice
1. Open side panel
2. Select voice from dropdown
3. Choice is saved automatically

### Adjust Speed
1. Open side panel
2. Drag speed slider (0.5x to 2.0x)
3. Default is 1.0x

### Change Server URL
1. Open side panel
2. Click "Advanced Settings"
3. Update Server URL
4. Click "Test Connection"

## Debugging

### View Extension Logs
1. Go to `chrome://extensions/`
2. Find Mockingbird
3. Click "service worker" link
4. Console opens with background script logs

### View Content Script Logs
1. Open any webpage
2. Press F12 (Developer Tools)
3. Look for messages starting with `[Mockingbird]`

### Common Error Messages

**"Failed to fetch voices"**
- Server is not running or unreachable
- Check server URL in Advanced Settings

**"TTS server error: 404"**
- Voice model file not found
- Verify voice files exist in `voices/` folder

**"No text to read"**
- Page might have no readable content
- Try selecting text manually first

## Next Steps

1. **Add Custom Voices**: See `voices/HOW_TO_ADD_VOICES.md`
2. **Replace Icons**: Add proper icon images to `icons/` folder
3. **Customize**: Edit colors/styles in CSS files
4. **Package**: Use `chrome://extensions/` → "Pack extension" for distribution

## Tips for Best Results

- Works best on article/blog pages with clear content
- Use "Read Selection" for specific paragraphs
- Adjust speed based on content complexity
- Try different voices for different use cases
- Keep Mockingbird server running in background

---

Need help? Check the main README or Mockingbird server documentation!
