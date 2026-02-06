# Adding Voices to PiperTTS Mockingbird

## Voices Folder Location

The `voices/` folder is located inside your `piper_tts_server/` directory:
```
piper_tts_server/
  voices/          <- Add your voice files here
    female/
    male/
  piper_manager_ui.py
  piper_server.py
  ...
```

## Finding Voices

### Listen to voice samples online
**Preview voices before downloading:**  
https://rhasspy.github.io/piper-samples/

### Download voices
**Full list of official Piper available voices:**  
https://huggingface.co/rhasspy/piper-voices/tree/main

## Community & Custom Voices

### Create Your Own Voice (Built-in)
You can create and train your own custom voices directly from the dashboard! This automated process handles everything from audio slicing to training. 

See the **Creating a Voice with Piper Training Web UI** section below for a step-by-step guide.

### Other Tools
Check out **TextyMcSpeechy**, a cool tool that claims to let you train Piper voices locally:  
https://github.com/domesticatedviking/TextyMcSpeechy  
*(Note: I haven't tested this tool myself, but I found it during my research and it seems cool enough to reference here!)*

### Find More Voices
Piper is very popular, so there are many community-created voices available online!  
You can find voices for popular characters and other unique styles by searching on GitHub and other platforms.

**Community Forum:**  
Here is a community forum where people share various Piper voices they've found:  
https://community.home-assistant.io/t/collections-of-pre-trained-piper-voices/915666

**⚠️ Disclaimer:** Always exercise caution when downloading files from the internet. Ensure you trust the source before downloading  files.

## Creating a Voice with Piper Training Web UI

Follow these steps to create a custom voice using the integrated training dashboard:

1. **Open Voice Studio**
   - Click **Voice Studio** in the sidebar to view your voice projects.

2. **Start a New Project**
   - Click the **+ New Voice** button.
   - Enter a **Voice Name** (Letters, numbers, and underscores only; **no spaces allowed**).
   - Select your desired **Quality** and **Gender**.
   - Choose if you want to **Start Training from Scratch** or use a base model (recommended for faster results).
   - Click **Create Dojo**.

3. **Prepare Your Dataset (Audio Slicer)**
   - Click **Upload Master Audio** and select a long recording of the voice you want to clone.
   - Use the **Tools & Settings** card in the following order:
     1. **Auto-Detect (Silence)**: Splits your large file into chunks.
     2. **Whitelist/Blacklist Filter**: Isolate the person's voice you are trying to clone.
     3. **Auto-Merge Gaps**: Combines segments for better flow.
     4. **Remove Tiny Segments**: Cleans up small audio artifacts.
   - Once the segments are ready, click **Next Step: Transcribe**.

4. **Auto-Transcription**
   - Click **Start AI Transcription**.
   - The system will automatically transcribe your clips. This takes about 5 minutes (a process that used to take people days to do manually!).
   - Review and edit the results if needed, then click **Next: Training Setup**.

5. **Training Setup**
   - Confirm your settings. The system scans and auto-fixes any bugs in the dataset before you start.
   - Click **Go to Cockpit** (preprocessing may take a couple of minutes).

6. **Training Cockpit**
   - The training page will open and **automatically start training**.
   - You can monitor the progress and click the **Stop** button when you wish to end the session.

## How to Add a Voice

1. **Download the voice files**
   - Each voice needs **two files**:
     - `voice-name.onnx` - The voice model file (~60MB)
     - `voice-name.onnx.json` - The voice configuration file (~5KB)
   - Both files must have matching names

2. **Organize your voices folder**
   - You can organize voices in subfolders (optional):
     ```
     voices/
       female/
         en_US-hfc_female-medium.onnx
         en_US-hfc_female-medium.onnx.json
       male/
         en_US-hfc_male-medium.onnx
         en_US-hfc_male-medium.onnx.json
       british/
         en_GB-alba-medium.onnx
         en_GB-alba-medium.onnx.json
     ```
   - Or put them all directly in the `voices/` folder:
     ```
     voices/
       en_US-hfc_female-medium.onnx
       en_US-hfc_female-medium.onnx.json
       en_US-hfc_male-medium.onnx
       en_US-hfc_male-medium.onnx.json
     ```

3. **Restart the manager UI**
   - Close and reopen the PiperTTS Mockingbird Dashboard.
   - The new voices will appear in the dropdown.
   - **Note:** The server caches the voice list for **60 seconds**. If you add a voice while the server is running, it may take up to a minute to appear in the API, or you can restart the server to clear the cache immediately.

4. **Select and test**
   - Choose the voice from the dropdown
   - Click "Test Voice" to hear it
   - The selected voice is saved automatically

## Tips

- **Quality levels**: Voices come in different quality levels (low, medium, high)
  - `low` - Faster, smaller files, lower quality
  - `medium` - Balanced (recommended)
  - `high` - Slower, larger files, best quality

- **Languages**: Piper supports many languages beyond English
  - Check the VOICES.md list for your language
  - Examples: `de_DE` (German), `es_ES` (Spanish), `fr_FR` (French)

- **Multi-speaker voices**: Some voices support multiple speakers
  - You can specify speaker ID in advanced settings (future feature)

## Troubleshooting

- **Voice not showing in dropdown?**
  - Make sure both `.onnx` and `.onnx.json` files are present
  - Restart the manager UI
  - Check the log: "Found X voice(s): ..."

- **Voice sounds wrong?**
  - Verify you downloaded both the `.onnx` AND `.onnx.json` files
  - The `.onnx.json` file must match the `.onnx` filename exactly

- **Server won't start?**
  - Large voice models need more memory
  - Try using "medium" quality voices instead of "high"
