# PiperTTS Mockingbird 🎤

**The easiest way to run high-quality local text-to-speech on your computer.**

PiperTTS Mockingbird is a simple, "all-in-one" tool that lets you use the incredibly fast Piper engine to turn text into speech. It's designed to be fast, private (no internet needed after setup), and easy enough for anyone to use.

> [!IMPORTANT]
> **⚖️ Legal & Ethical Notice:** This tool is intended for ethical use only. By using PiperTTS Mockingbird, you agree to only clone voices of consenting individuals (including yourself). Please read our [**Ethical Usage Disclaimer**](docs/ETHICAL_USAGE_DISCLAIMER.md) before proceeding.

---

## ⚡ Quick Start

No coding or terminal experience required. Just run the file for your system:

- **🪟 Windows:** Double-click [`Open PiperTTS Mockingbird (Windows).vbs`](Open%20PiperTTS%20Mockingbird%20(Windows).vbs)
- **🍎 macOS:** Double-click [`Open PiperTTS Mockingbird (macOS).command`](Open%20PiperTTS%20Mockingbird%20(macOS).command)
- **🐧 Linux:** Run [`Open PiperTTS Mockingbird (Linux).sh`](Open%20PiperTTS%20Mockingbird%20(Linux).sh)

**First Run:** The app will automatically set everything up for you. If you don't have Python 3.9+ installed, the launcher will attempt to install it for you automatically (Windows/macOS). The app then handles everything else: it creates a "safe space" (virtual environment) for itself, downloads the "brains" (Piper), and fetches a few starter voices (about 350MB total) all by itself. This might take a minute depending on your internet, but you only have to do it once!

---

## 🎮 How to Use the Dashboard

Once the window opens, you have everything you need in one place:

### 🔊 Testing Voices
*   **Pick a Voice:** Use the dropdown menu to choose who is speaking.
*   **Hear it:** Click **"Test Voice"** to hear a fun random sentence.
*   **Type your own:** Uncheck "Random" and type whatever you want in the text box.

### 🌐 Running the Server
The "Server" is what lets other apps (like Home Assistant or custom tools) talk to Mockingbird.
*   **Start/Stop:** Use the big buttons to turn the engine on and off.
*   **🟢 Green:** Everything is working!
*   **🔴 Red:** The engine is resting.
*   **⚙️ Autostart:** Check the **"Launch server automatically on Windows startup"** box if you want the server to start automatically whenever you turn on your computer.
*   **🔄 Auto-Restart:** You can also enable **"Auto-Restart server if it crashes"** to keep things running smoothly.

---

## 🔌 Integrations & Extensions

Mockingbird isn't just a dashboard—it can read the web for you and connect to your smart home! Check the `integrations/` folder for:

*   **🏠 Home Assistant:**
    *   **Live Connection:** Mockingbird automatically supports the **Wyoming Protocol**. Just add the Wyoming integration in your Home Assistant and point it to this computer.
    *   **One-Click Export:** You can package any voice as an "HA-Ready" file to manually import it into your Home Assistant server.
*   **🌐 Browser Extension:** Use the **Mockingbird Extension** to highlight text anywhere on the internet and hear it spoken by your local voices.
*   **📄 Google Docs Add-on:** Read your documents aloud directly from within Google Docs.

---

## 🥔 Hardware Requirements

**"Runs on a potato!"** 
One of the best things about this project is how lightweight it is. You don't need a fancy gaming PC or a GPU to *use* the voices.

*   **Works on:** Raspberry Pi 4, old laptops, budget desktops, and high-end PCs.
*   **Needs:** Just a basic CPU and about 2GB of RAM.
*   **Privacy:** Since it runs entirely on your machine, your text never leaves your computer.

*(Note: Training your **own** custom voice models from scratch does require a powerful PC with an NVIDIA GPU, but just listening to voices works on almost anything!)*

---

## ✂️ Breaking Innovation: The Dataset Slicer

Creating your own custom AI voice used to be a grueling process. Before this tool, you had to manually spend an entire weekend cutting audio files, labeling them, and transcribing every single sentence by hand. 

**Mockingbird automates the hard part.** We've included a powerful **Dataset Slicer** that handles the heavy lifting:

*   **Auto-Chunking:** Take a long audio file (a podcast, interview, or audiobook) and automatically split it into clean segments.
*   **Messy Audio? No Problem:** Our tools help you handle "noisy" source material. Even if your recording has background music or other speakers, you can easily filter those out and isolate only the high-quality segments for training.
*   **Auto-Transcription:** The tool automatically transcribes all your audio segments using AI.
*   **Built for Everyone:** We obsessed over the UI to make it as intuitive as possible. You don’t need to be a software engineer or a data scientist; if you can click a mouse, you can build a professional-grade voice dataset.
*   **Organized & Portable:** Everything is saved into a perfectly organized folder with high-quality WAV files and a standard metadata CSV. Theoretically, you could use this tool just to build datasets for other voice trainers—simply copy and paste the folder!
*   **Weekend to Hour:** What used to take **48+ hours of manual work** now takes **less than an hour** of passive processing.

If you have a clean recording of a voice, you can now go from raw audio to a training-ready dataset in minutes, not days.

---

## 📂 Adding More Voices

Want more variety? Click the **"How to add voices?"** button in the app or see the [**Voice Addition Guide**](voices/HOW_TO_ADD_VOICES.md). 

We support three quality levels:
1.  **High:** Best sound, uses a bit more power.
2.  **Medium:** The "Sweet Spot" (Recommended).
3.  **Low:** Extreme speed, works on the oldest hardware.

---

## 🔍 Troubleshooting

**Something not working?**
- **Server won't start?** The app tries to install Python automatically, but if you see errors, you can manually download it from [python.org/downloads](https://www.python.org/downloads/). Make sure to check "Add Python to PATH" during installation.
- **No voices?** The app downloads them on the first run. Make sure your internet is connected for that first launch.
- **Buttons not working?** Look at the logs at the bottom of the dashboard—they usually give a hint about what's wrong.

---

## 🚀 Roadmap & Philosophy

- **My Mission:** I built this to democratize local AI. My goal is to make it so average people—not just software engineers—can set up and enjoy high-quality local text-to-speech without any technical headache.
- **High-Fidelity "Turbo" Mode:** One day I might add **Kokoro-82M** for users who want the absolute highest quality speech.
- **Speed First:** I chose **Piper** because it is the fastest local engine available. My goal is to keep this accessible even for people with older hardware.

---

## 🛠️ For Power Users & Developers

If you are a developer looking for the API documentation, command-line setup, or security details, please see our technical documentation:

*   **[Technical Setup & API Guide](src/DEVELOPER.md)** (Requirements, cURL examples, etc.)
*   **[Security Overview](docs/SECURITY_HARDENING.md)** (CORS, Sanitization, etc.)
*   **[User Manual](docs/WEBUI_USER_MANUAL.md)** (Detailed Web Dashboard guide)
*   **[Changelog](docs/CHANGELOG.md)** (Recent updates and version history)

---

## 📜 License & Acknowledgments

This project is licensed under the MIT License. It is powered by the amazing [Piper TTS](https://github.com/rhasspy/piper) engine.

**Credits:**
- A special thanks to **TextyMcSpeechy**! The voice training pipeline in this project is based on [TextyMcSpeechy](https://github.com/domesticatedviking/TextyMcSpeechy), which served as the foundation for our training backend.

---
*Created with ❤️ to make local AI accessible to everyone.*
