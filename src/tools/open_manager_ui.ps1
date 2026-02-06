# PowerShell script to launch the PiperTTS Mockingbird Dashboard.
# This script handles virtual environment setup, dependency installation, and launches the UI using pythonw.exe (no console).

$ErrorActionPreference = 'Stop'

# Determine directory structure
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$srcDir = Split-Path -Parent $scriptDir
$rootDir = Split-Path -Parent $srcDir
Set-Location $srcDir

# Logging setup for troubleshooting launch issues
$logPath = Join-Path $rootDir 'open_manager_ui.log'
function Write-Log([string]$Message) {
  $ts = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
  Add-Content -Path $logPath -Value "[$ts] $Message"
}

Write-Log "--- Launch start ---"
Write-Log "SrcDir: $srcDir"
Write-Log "RootDir: $rootDir"

# Check if the UI is already running and bring it to the front if it is
try {
    Add-Type @"
using System;
using System.Runtime.InteropServices;
public class WinAPI {
    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")]
    public static extern bool IsIconic(IntPtr hWnd);
    [DllImport("user32.dll", SetLastError=true)]
    public static extern IntPtr FindWindow(string lpClassName, string lpWindowName);
}
"@
    
    # Try to find existing window with common title variations
    $titles = @("PiperTTS Mockingbird • Manager Dashboard", "PiperTTS Mockingbird")
    $hwnd = [IntPtr]::Zero
    
    foreach ($title in $titles) {
        $hwnd = [WinAPI]::FindWindow($null, $title)
        if ($hwnd -ne [IntPtr]::Zero) {
            Write-Log "Found existing window: $title"
            if ([WinAPI]::IsIconic($hwnd)) {
                [WinAPI]::ShowWindow($hwnd, 9)  # SW_RESTORE
            }
            [WinAPI]::SetForegroundWindow($hwnd)
            Write-Log "Brought window to front"
            exit 0
        }
    }
} catch {
    Write-Log "Error checking for existing window: $_"
    # Continue with launch
}

try {
  # Define virtual environment paths
  $venvDir = Join-Path $rootDir '.venv'
  $pythonExe = Join-Path $venvDir 'Scripts\python.exe'
  $pythonWExe = Join-Path $venvDir 'Scripts\pythonw.exe'

  # Create virtual environment if missing
  if (-not (Test-Path $pythonExe)) {
    Write-Log "Venv not found. Creating venv in $venvDir"

    # Prefer the Windows Python launcher if available
    $bootstrap = Get-Command py -ErrorAction SilentlyContinue
    if ($bootstrap) {
      & py -3 -m venv $venvDir
    } else {
      $bootstrap = Get-Command python -ErrorAction SilentlyContinue
      if (-not $bootstrap) {
        throw "Python not found on PATH. Install Python 3 or ensure 'py' or 'python' is available."
      }
      & python -m venv $venvDir
    }
  }

  if (-not (Test-Path $pythonExe)) {
    throw "Venv creation did not produce $pythonExe"
  }

  # Ensure dependencies are installed
  Write-Log "Installing/updating Python deps"
  & $pythonExe -m pip install --upgrade pip | Out-Null
  & $pythonExe -m pip install -r (Join-Path $srcDir 'requirements.txt') | Out-Null

  if (-not (Test-Path $pythonWExe)) {
    throw "pythonw.exe not found at $pythonWExe"
  }

  $uiPath = Join-Path $srcDir 'piper_manager_ui.py'
  if (-not (Test-Path $uiPath)) {
    throw "UI script not found: $uiPath"
  }

  # Launch the UI script using pythonw.exe to avoid a persistent console window
  $uiArg = '"' + $uiPath + '"'
  Write-Log "Starting UI via pythonw.exe"
  Write-Log "Cmd: $pythonWExe $uiArg"
  $proc = Start-Process -FilePath $pythonWExe -ArgumentList $uiArg -WorkingDirectory $srcDir -PassThru
  Write-Log "UI started (pid=$($proc.Id))"

  # Brief wait to check if the process crashes immediately
  Start-Sleep -Milliseconds 1200
  $proc.Refresh()
  if ($proc.HasExited) {
    if ($proc.ExitCode -eq 0) {
        Write-Log "UI process exited with success (likely already running or performed a handoff)."
        exit 0
    }
    Write-Log "UI process exited early (exitCode=$($proc.ExitCode))."
    $uiLog = Join-Path $srcDir 'piper_manager_ui.log'
    throw "Manager UI exited immediately (code $($proc.ExitCode)). Check the log: $uiLog"
  }

  Write-Log "--- Launch ok ---"
}
catch {
  Write-Log "ERROR: $($_ | Out-String)"
  Write-Log "--- Launch failed ---"
  throw
}
