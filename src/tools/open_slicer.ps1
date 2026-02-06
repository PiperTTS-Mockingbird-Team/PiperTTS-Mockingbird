# PowerShell script to launch the Dataset Slicer UI.

$ErrorActionPreference = 'Stop'

# Determine directory structure
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$srcDir = Split-Path -Parent $scriptDir
$rootDir = Split-Path -Parent $srcDir
Set-Location $srcDir

# Define paths
# Use root .venv
$PYTHON_EXE = Join-Path $rootDir ".venv\Scripts\pythonw.exe"

$UI_SCRIPT = Join-Path $srcDir "tools\dataset_slicer_ui.py"

# Ensure venv exists
if (-not (Test-Path $PYTHON_EXE)) {
    Write-Host "Virtual environment not found. Please run setup first." -ForegroundColor Red
    exit 1
}

Start-Process -FilePath $PYTHON_EXE -ArgumentList "`"$UI_SCRIPT`""
