# PowerShell script to start the Piper TTS server.
# This script ensures the virtual environment exists, installs dependencies, and launches the server.

$ErrorActionPreference = 'Stop'

# Determine the source directory relative to this script
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$srcDir = Split-Path -Parent $scriptDir
$rootDir = Split-Path -Parent $srcDir
Set-Location $srcDir

# Define virtual environment paths
$venvDir = Join-Path $rootDir '.venv'
$pythonExe = Join-Path $venvDir 'Scripts\python.exe'

# Create virtual environment if it doesn't exist
if (-not (Test-Path $pythonExe)) {
  Write-Host "Creating venv in $venvDir ..."
  python -m venv $venvDir
}

# Ensure dependencies are up to date
Write-Host "Installing/updating Python deps..."
& $pythonExe -m pip install --upgrade pip
& $pythonExe -m pip install -r (Join-Path $srcDir 'requirements.txt')

# Launch the FastAPI server using uvicorn
Write-Host "Starting Piper server on http://127.0.0.1:5002 ..."
& $pythonExe -m uvicorn piper_server:app --host 127.0.0.1 --port 5002
