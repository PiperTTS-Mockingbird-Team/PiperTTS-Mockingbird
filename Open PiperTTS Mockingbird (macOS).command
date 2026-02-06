#!/bin/bash
# PiperTTS Mockingbird Manager Launcher for macOS
# Double-click this file to launch the Manager Dashboard

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Change to the project root directory
cd "$SCRIPT_DIR"

# Check for Python 3
if ! command -v python3 &> /dev/null; then
    echo "Python 3 is not installed."
    echo ""
    echo "Attempting to install via Homebrew..."
    
    # Check if Homebrew is installed
    if command -v brew &> /dev/null; then
        echo "Installing Python 3 via Homebrew..."
        brew install python3
        
        # Check if installation succeeded
        if ! command -v python3 &> /dev/null; then
            echo "Installation failed. Please visit: https://www.python.org/downloads/"
            open "https://www.python.org/downloads/"
            exit 1
        fi
    else
        echo "Homebrew not found. Opening Python download page..."
        echo "After installing Python, run this script again."
        open "https://www.python.org/downloads/"
        exit 1
    fi
fi

# Setup virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate environment and install dependencies
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r src/requirements.txt

# Launch the Manager UI
python src/piper_manager_ui.py
