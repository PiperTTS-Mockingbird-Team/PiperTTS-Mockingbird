# Mockingbird - Local TTS Reader Extension

A privacy-first Chrome extension that reads webpages aloud using your local Piper TTS server. No data ever leaves your machine!

## Features

✨ **Website Reading**
- Read entire webpages with one click
- Read selected text by highlighting and clicking the floating button
- **NEW:** Click any paragraph to start reading from that point
- **NEW:** Right-click text for quick read menu
- Smart content extraction focuses on main article text
- **NEW:** OCR support - Extract and read text from images
- **NEW:** Optimized parsing for 10+ popular sites:
  - Google Docs
  - Wikipedia (removes references, nav boxes)
  - Reddit (new and old Reddit)
  - Medium
  - Twitter/X (tweets and threads)
  - LinkedIn (posts and articles)
  - Substack newsletters
  - GitHub (README, issues, PRs)
  - PDF viewers (basic support)
  - News sites and blogs
- Sentence-by-sentence reading with visual highlighting

🎛️ **Full Playback Controls**
- Play/Pause, Stop, Skip Forward/Backward
- **NEW:** Skip forward/backward by 10 seconds (Alt+Left/Right)
- **NEW:** Jump to percentage (0%, 25%, 50%, 75%)
- Adjustable reading speed (0.5x - 2.0x)
- Volume control
- **NEW:** Sleep timer (5, 10, 15, 30, 60 minutes)
- Keyboard shortcuts: `Alt+A` (Play/Pause), `Alt+S` (Stop), `Alt+←` (Back 10s), `Alt+→` (Forward 10s)

🔊 **Voice Selection**
- Automatically detects all voices from your Piper server
- Support for multiple languages and quality levels
- Easy voice switching from the side panel

🎨 **Beautiful UI**
- Modern gradient design
- Side panel with full controls
- Floating "Read" button on text selection
- Real-time text highlighting as it reads
- **NEW:** Word-by-word highlighting option
- **NEW:** Auto-scroll to follow reading (toggle on/off)
- Clean, minimalist overlay controls

📚 **Library & Reading Management**
- **NEW:** Save pages to your reading library
- **NEW:** Resume reading from where you left off
- **NEW:** Reading history tracking
- Organize articles for later listening

🔒 **100% Private**
- All processing happens locally on your machine
- No data sent to the cloud
- No tracking, no analytics, no external connections
- Works completely offline (once voices are downloaded)

## Installation

### 1. Prerequisites
Make sure your Piper TTS server is running:
- Server should be accessible at `http://localhost:5002`
- See the main README for server setup instructions

### 2. Load Extension in Chrome

1. Open Chrome and navigate to `chrome://extensions/`
2. Enable "Developer mode" (toggle in top-right corner)
3. Click "Load unpacked"
4. Select the `integrations/mockingbird_extension` folder
5. The extension should now appear in your toolbar!

### 3. First-Time Setup

1. Click the Mockingbird icon in your toolbar
2. The side panel will open
3. Check that "Server connected" appears (green dot)
4. Select your preferred voice
5. Adjust speed and volume to taste
6. You're ready to go!

## Usage

### Reading a Full Page
1. Navigate to any webpage
2. Click the Mockingbird icon or press `Alt+A`
3. The extension will read the main content

### Reading Selected Text
1. Highlight any text on a page
2. Click the floating "🔊 Read" button that appears
3. Or press `Alt+A` after selecting
4. **NEW:** Or right-click and select "Read with Mockingbird"

### Click-to-Listen
**NEW:** Click any paragraph on a webpage to start reading from that point forward!

### OCR - Extract Text from Images
**NEW:** Extract and read text from images on any webpage!

1. Right-click any image on a webpage
2. Select "Extract text from image (OCR)"
3. Wait a moment while the text is extracted
4. A modal will appear with the extracted text
5. Choose to:
   - **Read Aloud**: Click the "🔊 Read Aloud" button
   - **Copy**: Click the "📋 Copy Text" button to copy to clipboard

**OCR Settings** (in Advanced Settings):
- **Language**: Choose OCR language (English, Spanish, French, German, etc.)
- **Auto-read**: Automatically read extracted text (skip the modal)

**Supported Languages:**
- English, Spanish, French, German, Italian, Portuguese
- Russian, Arabic, Chinese Simplified, Japanese, Korean
- And many more...

### Playback Controls
- **Play/Pause**: `Alt+A` or click ⏯ button
- **Stop**: `Alt+S` or click ⏹ button
- **Skip Forward**: Click ⏭ button or `Alt+→` (10 seconds)
- **Skip Backward**: Click ⏮ button or `Alt+←` (10 seconds)
- **Jump to Position**: Use 0%, 25%, 50%, 75% buttons in side panel

### Sleep Timer
1. Open the side panel
2. Select sleep timer duration (5, 10, 15, 30, or 60 minutes)
3. Reading will automatically stop when timer expires

### Save to Library
1. While on a page you want to save, click "Save to Library" in the side panel
2. Or right-click anywhere on the page and select "Save page to library"
3. Access your saved pages by clicking "View Library"
4. Continue reading from where you left off

### Adjusting Settings
Open the side panel to:
- Change voice
- Adjust reading speed (0.5x - 2.0x)
- Change volume
- Toggle auto-scroll on/off
- Configure custom server URL

## Troubleshooting

### "Server offline" message
- Make sure your Piper TTS server is running on port 5002
- Run the PiperTTS Mockingbird Dashboard and start the server
- Check Advanced Settings to verify server URL

### No voices available
- Ensure you have voice files in your `voices/` folder
- See `voices/HOW_TO_ADD_VOICES.md` for instructions
- Restart the Piper server after adding voices

### Extension not working on a page
- Some pages (like chrome:// URLs) block extensions
- Try refreshing the page
- Check the browser console (F12) for errors

### Highlighting not working
- Some websites use shadow DOM which can interfere
- The audio will still play, highlighting just might not work
- This is a known limitation with complex web apps

## Development

Built with:
- Chrome Extension Manifest V3
- Vanilla JavaScript (no frameworks)
- FastAPI backend (Piper server)
- Local Piper TTS engine

## Contributing

Want to improve Mockingbird? Contributions welcome:
- Report bugs as issues
- Suggest features
- Submit pull requests

## License

MIT License - see main project LICENSE file

## Credits

- Built for [Piper TTS Server](https://github.com/rhasspy/piper)
- Created as part of the Piper TTS Server project

---

**Enjoy reading the web with complete privacy! 🔒📖**
