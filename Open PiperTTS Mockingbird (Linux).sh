#!/bin/bash
# PiperTTS Mockingbird Manager Launcher for Linux
# Run this script to launch the Manager Dashboard

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Change to the project root directory
cd "$SCRIPT_DIR"

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo "Python 3 is not installed."
    echo ""
    echo "Please install Python 3.9 or newer:"
    echo "  Ubuntu/Debian: sudo apt install python3 python3-venv python3-pip"
    echo "  Fedora: sudo dnf install python3 python3-pip"
    echo "  Arch: sudo pacman -S python python-pip"
    echo ""
    read -p "Press Enter to exit..."
    exit 1
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
