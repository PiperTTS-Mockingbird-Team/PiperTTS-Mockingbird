#!/bin/bash
# PiperTTS Mockingbird Manager Launcher for macOS
# Double-click this file to launch the Manager Dashboard

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Change to the project root directory
cd "$SCRIPT_DIR"

# Launch the Manager UI
python3 src/piper_manager_ui.py
