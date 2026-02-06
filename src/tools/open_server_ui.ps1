# PowerShell script to launch the Piper Server UI (Server Only).
# This script handles virtual environment setup and launches the UI using pythonw.exe (no console).

$ErrorActionPreference = 'Stop'

# Determine directory structure
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$srcDir = Split-Path -Parent $scriptDir
$rootDir = Split-Path -Parent $srcDir
Set-Location $srcDir

# Logging setup for troubleshooting launch issues
$logPath = Join-Path $rootDir 'open_server_ui.log'
function Write-Log([string]$Message) {
  $ts = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
  Add-Content -Path $logPath -Value "[$ts] $Message"
}

Write-Log "--- Launch start (Server Only) ---"
Write-Log "SrcDir: $srcDir"
Write-Log "RootDir: $rootDir"

# Check if the UI is already running and bring it to the front if it is
try {
    $wshell = New-Object -ComObject WScript.Shell
    if ($wshell.AppActivate("Piper TTS Server")) {
        Write-Log "UI already running. Brought existing window to front."
        exit 0
    }
} catch {
    Write-Log "Error checking for existing window: $_"
}

# Ensure .venv exists
$venvDir = Join-Path $rootDir '.venv'
if (-not (Test-Path $venvDir)) {
    Write-Log "Venv not found. Please run the full Manager first to set up environment."
    exit 1
}

# Run the UI script with pythonw (no console window)
$pythonw = Join-Path $venvDir 'Scripts\pythonw.exe'
$scriptPath = Join-Path $srcDir 'piper_server_ui.py'

if (-not (Test-Path $pythonw)) {
    Write-Log "Pythonw not found at $pythonw"
    exit 1
}

Write-Log "Starting UI via pythonw.exe"
$cmdArgs = "`"$scriptPath`""
Write-Log "Cmd: $pythonw $cmdArgs"

try {
    # Start-Process allows us to detach completely
    Start-Process -FilePath $pythonw -ArgumentList $cmdArgs -WindowStyle Hidden
    Write-Log "UI started"
} catch {
    Write-Log "Start-Process failed: $_"
    exit 1
}

Write-Log "--- Launch ok ---"
