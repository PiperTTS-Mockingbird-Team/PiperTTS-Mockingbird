# PiperTTS Mockingbird Web Dashboard - User Manual

Welcome to the **PiperTTS Mockingbird Web Dashboard**! This guide will help you navigate the interface and make the most of your text-to-speech experience.

---

## 🚀 Getting Started

### Accessing the Dashboard

1. Start PiperTTS Mockingbird (either through the Python Dashboard or the Windows shortcut)
2. Open your web browser and navigate to `http://127.0.0.1:5002`
3. The dashboard will load automatically

---

## 📋 Main Navigation

The dashboard has several main tabs accessible from the left sidebar:

### **Overview Tab** 🏠
Your main control center with quick access to all features.

**Key Features:**
- **Voice Testing Panel** - Test any voice with custom text or random phrases
- **Speed Control** - Adjust playback speed (0.75x to 2x) without regenerating audio
- **Quick Actions** - Fast access to common tasks
- **System Health** - Monitor server status and run diagnostics
- **Recent Activity** - View the latest synthesis operations

### **Voices Tab** 🎤
Manage your voice library and load different models.

**Actions Available:**
- View all installed voices with file sizes
- Add custom nicknames to voices for easy identification
- Test individual voices with a play button
- Load/switch between different voice models
- Open the voices folder for file management

### **Training Tab** 🎓
Create and manage voice training projects (Voice Dojos).

**Workflow:**
1. **Create a New Dojo** - Click "Create New Voice Project" modal and enter project details
2. **Clip Audio** - Use the advanced audio slicer to prepare your dataset
3. **Transcribe** - Auto-generate or manually edit transcriptions
4. **Setup** - Review settings and run preprocessing (via "Launch Training" button)
5. **Train** - Start the training process and monitor progress

**Project Actions:**
- Launch Training - Opens the setup step to verify settings and dataset readiness
- Clip Audio - Opens the audio slicer tool to prepare your dataset
- Transcribe - Auto-starts Whisper transcription for your audio clips
- Folder - Opens the project folder on your computer
- Legacy Slicer - Opens the original Python-based dataset slicer tool

### **Logs Tab** 📜
View detailed system logs with color-coded severity levels.

**Log Levels:**
- 🔴 **ERROR** - Critical issues requiring attention
- 🟡 **WARNING** - Non-critical issues or alerts
- 🔵 **INFO** - General operational messages

**Features:**
- Auto-scrolling when viewing latest logs
- Stack trace formatting for debugging
- Timestamp and level badges for easy scanning

### **Storage Tab** 💾
Manage disk space and clean up old training data.

**Sub-sections:**
- **Overview** - Total space used by Piper TTS
- **Training Artifacts** - View and delete old checkpoints/models
- **Docker Management** - Clean up training engine images

### **Settings Tab** ⚙️
Configure global application preferences.

**Available Settings:**
- Server host and port configuration
- Default voice selection
- Sentence silence duration
- Auto-restart on crash
- System information display

---

## ⚡ Quick Actions Panel

Located on the Overview tab for instant access:

### **Files** 💾
Opens the Storage Management tool to view disk usage and clean up old files.

### **Voices** 🎤
Opens the `voices` folder in your file explorer for manual voice file management.

### **Download** ☁️
Triggers the model download/update process. Useful for getting new voices from the Piper repository.

### **Guide** 📖
Opens this user manual in your browser for quick reference.

### **Add Voices Guide** 📘
Opens detailed instructions on how to add new voice models to your system.

### **Logs Folder** 📁
Opens the system logs folder on your computer for troubleshooting and debugging.

### **Manager** 🔧
**IMPORTANT:** Opens the Python Manager GUI where you can:
- Stop the web server completely
- View advanced system settings
- Access additional management tools
- Monitor server processes

### **Restart** 🔄
Restarts the TTS server. Use this when:
- Applying new configuration changes
- Recovering from errors
- Clearing memory/cache

---

## 🎙️ Using the Voice Testing Panel

### Basic Text-to-Speech

1. **Select a Voice** - Choose from the dropdown menu at the top
2. **Enter Text** - Type your message in the text box
   - Use the "Random" checkbox to generate test phrases automatically
3. **Adjust Speed** - Click one of the speed buttons (0.75x, 1x, 1.25x, 1.5x, 2x)
4. **Click "Test Voice"** - Your audio will generate and play automatically

### Speed Control

The speed control system works in two modes:
- **Live Playback Adjustment** - Change speed during or after playback without regenerating
- **High Quality** - All audio is generated at 1x speed for best quality, then played back at your selected rate

### Downloading Audio

After generating speech:
1. Click the **Download** button in the audio player
2. The file will be saved with a name based on your text content
3. Format: WAV (high quality, uncompressed)

---

## 🎓 Training Your Own Voice

### Phase 1: Dataset Preparation

**Requirements:**
- 10-30 minutes of clear audio recordings
- Single speaker only
- Minimal background noise
- Consistent recording quality

**Steps:**
1. Create a new Voice Dojo from the Training tab
2. Upload or record your audio files
3. Use the **Audio Slicer** to split recordings into 2-10 second clips
4. Review and adjust clip boundaries for clean cuts

### Phase 2: Transcription

The system offers two methods:

**Automatic Transcription:**
- Uses Whisper AI to generate text automatically
- Best for English and major languages
- Saves time but may need manual review

**Manual Transcription:**
- Type or paste transcriptions for each clip
- Required for perfect accuracy
- Edit in the transcription table

### Phase 3: Training Setup

Before training begins:
1. **Select Gender** - Male or Female (affects voice characteristics)
2. **Choose Quality** - Low/Medium/High (higher = longer training)
3. **Set Language** - Language code (e.g., "en-us" for English)
4. **Run Preprocessing** - Validates dataset and prepares files

### Phase 4: Training Execution

**Monitor Progress:**
- Live training terminal output
- Step counter and time estimates
- GPU utilization graphs (if available)

**Checkpoint Management:**
- Training saves progress every N epochs
- Configure intervals in advanced settings
- Old checkpoints auto-delete based on retention settings

**Safety Features:**
- Thermal protection (stops if GPU overheats)
- Disk space monitoring (stops if running out of space)
- Auto-save on interruption

---

## 🔧 System Health & Diagnostics

### Running Diagnostics

From the Overview tab:
1. Scroll to the **System Health** section
2. Click **"Run Diagnostic Test"**
3. Review results for any issues

**Common Checks:**
- ✅ Server connectivity
- ✅ Voice files loaded correctly
- ✅ Disk space available
- ✅ Dependencies installed

### Status Indicators

**Green Dot** 🟢 - All systems healthy
**Red Dot** 🔴 - Issues detected (run diagnostics)

---

## 📁 Storage Management

### Understanding Disk Usage

The Storage tab shows:
- **Total Managed Size** - All data used by Piper TTS
- **Training Artifacts** - Checkpoints, models, and logs from training
- **Docker Images** - Training engine containers

### Cleaning Up Space

**To Delete Old Training Data:**
1. Go to **Storage → Training Artifacts**
2. Review the list of training projects
3. Click **Delete** next to projects you no longer need
4. Confirm deletion (this is permanent!)

**To Remove Docker Engine:**
- Click **"Delete Training Engine"** to free up ~500MB-2GB
- Only do this if you're not planning to train voices soon
- You can re-download it later when needed

---

## 🎨 Customizing Your Experience

### Voice Nicknames

Give your voices memorable names:
1. Go to the **Voices** tab
2. Click in the nickname field (tag icon)
3. Type a friendly name (e.g., "Morgan" instead of "en_US-lessac-medium")
4. Changes save automatically and appear everywhere

### Server Startup

**Auto-start on Windows Boot:**
1. Check the **"Launch server automatically on Windows startup"** checkbox in the Overview tab's Preferences section
2. Server will start automatically when you log in
3. Mockingbird needs this server to work

Note: Desktop shortcut management is handled through the Python Manager application, not the web dashboard.

---

## 🐛 Troubleshooting

### Common Issues

**Problem:** Voice doesn't play after clicking "Test Voice"
- **Solution:** Check that your browser allows audio playback
- Try clicking inside the page first (browsers require user interaction)

**Problem:** Training fails to start
- **Solution:** Run preprocessing first from the Setup step
- Ensure you have at least 5GB free disk space
- Check that Docker is running (for GPU training)

**Problem:** Server won't start
- **Solution:** Check if another program is using port 5002
- Open the Python Manager and click "Restart Server"
- Review logs folder for error messages

**Problem:** Can't find downloaded voices
- **Solution:** Click the "Voices" quick action button
- It opens the voices folder directly in file explorer

### Getting Help

**Log Files:**
- Click **"Logs Folder"** quick action
- Look for `piper_server.log` for web server issues
- Look for `piper_manager_ui.log` for manager issues

**System Information:**
- Run diagnostics from the System Health panel
- Copy the output to share with support

---

## 🔐 Security & Privacy

### Local-Only Operation

- Piper TTS runs **entirely on your computer**
- No data is sent to external servers
- Your voice recordings and models stay private
- Internet only needed for initial downloads

### Network Access

- The web server binds to `127.0.0.1` (localhost only)
- Not accessible from other computers by default
- Safe to run on public WiFi networks

---

## 🚦 Best Practices

### For Best Audio Quality

1. ✅ Use high-quality voice models (marked "high quality")
2. ✅ Keep text under 500 characters per generation
3. ✅ Use proper punctuation for natural pauses
4. ✅ Test multiple voices to find the best match for your needs

### For Training Success

1. ✅ Record in a quiet room with minimal echo
2. ✅ Use consistent microphone placement
3. ✅ Speak at a natural pace (not too fast or slow)
4. ✅ Include varied sentence structures and emotions
5. ✅ Aim for 20+ minutes of total audio for best results

### For System Performance

1. ✅ Close unused training projects when done
2. ✅ Clean up old checkpoints regularly
3. ✅ Monitor disk space before starting training
4. ✅ Restart server if it becomes slow or unresponsive

---

## 📚 Additional Resources

### File Locations

- **Voices:** `piper_tts_server/voices/`
- **Training Projects:** `piper_tts_server/training/make piper voice models/tts_dojo/`
- **Logs:** `piper_tts_server/logs/`
- **Config:** `piper_tts_server/src/config.json`

---

## 💡 Tips & Tricks

### Speed Training Workflow

1. Use **"Clip Audio"** → **"Transcribe"** → **"Train"** buttons for quick navigation
2. The transcription step auto-starts if no metadata exists
3. Preprocessing runs automatically when you start training (if needed)

### Audio Slicer Mastery

- **Click and drag** on the waveform to create new segment regions
- **Double-click** a segment to focus and play it
- **Delete key** or click the **Delete button** to remove selected segments
- Use the **Auto-detect Silences** feature for automatic slicing
- Zoom in/out with the controls for precise editing
- Use keyboard shortcuts: Space to play/pause, Delete to remove segments

### Voice Testing Tips

- Use the random phrases to hear voice character quickly
- Test with different punctuation styles: "Hello." vs "Hello!" vs "Hello?"
- Try numbers, dates, and abbreviations to check pronunciation
- Download and compare multiple voices side-by-side

---

## 🎉 Advanced Features

### Custom Voice Configuration

Advanced users can edit `config.json` directly:
- Adjust noise suppression levels
- Change sentence length limits
- Modify synthesis parameters

### API Access

The dashboard runs on a REST API available at:
- **Health Check:** `GET /health`
- **Generate Speech:** `POST /api/tts`

See the server code for additional endpoints available for integration into your own projects.

---

## ✨ Enjoy Your TTS Experience!

This dashboard is designed to make text-to-speech generation and custom voice training as smooth as possible. If you have questions, suggestions, or find issues, check the logs first, then reach out to support.

**Happy synthesizing! 🎤✨**
