#!/bin/bash
# This script sets up the environment and starts the PiperTTS Mockingbird Dashboard on Linux/macOS.
set -e

# Get the absolute path to the directory where this script is located
TOOLS_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
SRC_DIR="$( cd "$TOOLS_DIR/.." && pwd )"
VENV_DIR="$SRC_DIR/.venv"

# Detect the available Python executable (prefer python3)
if command -v python3 &>/dev/null; then
    PYTHON_CMD=python3
else
    PYTHON_CMD=python
fi

# Create a virtual environment if it doesn't already exist
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment in $VENV_DIR ..."
    $PYTHON_CMD -m venv "$VENV_DIR"
fi

# Activate the virtual environment
source "$VENV_DIR/bin/activate"

# Ensure all required Python dependencies are installed and up to date
echo "Installing/updating Python dependencies..."
pip install --upgrade pip
pip install -r "$SRC_DIR/requirements.txt"

# Start the PiperTTS Mockingbird graphical user interface
echo "Starting PiperTTS Mockingbird Dashboard..."
cd "$SRC_DIR"

# macOS specific: Bring to front if already running
if [[ "$OSTYPE" == "darwin"* ]]; then
    osascript -e 'tell application "System Events" to set frontmost of every process whose name is "Python" to true' 2>/dev/null || true
fi

python piper_manager_ui.py
