# open_training_dashboard.ps1: Launch the Training Dashboard UI

# Get the directory of this script (src\tools)
$TOOLS_DIR = Split-Path -Parent $MyInvocation.MyCommand.Definition
$SRC_DIR = Split-Path -Parent $TOOLS_DIR
$ROOT_DIR = Split-Path -Parent $SRC_DIR
Set-Location -Path $ROOT_DIR

# Define paths
# Use root .venv
$PYTHON_EXE = Join-Path $ROOT_DIR ".venv\Scripts\pythonw.exe"

$DASHBOARD_SCRIPT = Join-Path $SRC_DIR "training_dashboard_ui.py"

# Ensure venv exists
if (-not (Test-Path $PYTHON_EXE)) {
    $PYTHON_EXE = "pythonw.exe"
}

# Run the dashboard and log errors if it fails to start
$logFile = Join-Path $ROOT_DIR "training_dashboard.log"
Start-Process -FilePath $PYTHON_EXE -ArgumentList "`"$DASHBOARD_SCRIPT`"" -RedirectStandardError $logFile

