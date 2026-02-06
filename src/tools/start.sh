#!/bin/bash
# This script sets up the environment and starts the Piper TTS server on Linux/macOS.
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

# Start the Piper server using Uvicorn
echo "Starting Piper server on http://127.0.0.1:5002 ..."
cd "$SRC_DIR"
python -m uvicorn piper_server:app --host 127.0.0.1 --port 5002
