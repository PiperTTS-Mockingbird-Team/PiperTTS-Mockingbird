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
    
    # Show basic feedback since this part is slow
    Add-Type -AssemblyName System.Windows.Forms
    $msg = "PiperTTS Mockingbird is setting up a fresh virtual environment.`n`nThis may take a minute or two on the first run. Please wait..."
    [System.Windows.Forms.MessageBox]::Show($msg, "First Time Setup", [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Information)

    # Function to check if a python executable is compatible (< 3.13)
    function Is-PythonCompatible($exe) {
      $path = Get-Command $exe -ErrorAction SilentlyContinue
      if (-not $path) { return $false }
      # Get version info
      $version = & $path.Source -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
      if ($version -and [float]$version -lt 3.13 -and [float]$version -ge 3.9) { return $true }
      return $false
    }

    $basePython = $null

    # 1. Search for compatible version via 'py' launcher
    if (Get-Command py -ErrorAction SilentlyContinue) {
      foreach ($ver in @("3.12", "3.11", "3.10", "3.9")) {
        & py -$ver --version > $null 2>&1
        if ($LASTEXITCODE -eq 0) {
          $basePython = "py -$ver"
          Write-Log "Found compatible Python $ver via py launcher"
          break
        }
      }
    }

    # 2. Check default 'python' command
    if (-not $basePython -and (Is-PythonCompatible "python")) {
      $basePython = "python"
      Write-Log "Found compatible version via 'python' command"
    }

    # 3. If still nothing compatible, try to auto-install (3.12) via winget
    if (-not $basePython) {
      $winget = Get-Command winget -ErrorAction SilentlyContinue
      if ($winget) {
        Write-Log "No compatible Python (3.9-3.12) found. Attempting auto-install of 3.12 via winget..."
        
        $dlMsg = "A compatible version of Python (3.12) is required for audio processing but was not found.`n(Current system Python is either missing or too new i.e. 3.13+)`n`n" +
                 "Would you like to automatically download and install Python 3.12 now via Windows Package Manager (winget)?`n`n" +
                 "This is a one-time automated setup step."
        $dlResponse = [System.Windows.Forms.MessageBox]::Show($dlMsg, "Python Download Required", [System.Windows.Forms.MessageBoxButtons]::YesNo, [System.Windows.Forms.MessageBoxIcon]::Question)
        
        if ($dlResponse -eq 'Yes') {
          Write-Log "Starting winget install..."
          # Start winget and wait for it to finish
          $proc = Start-Process "winget" -ArgumentList "install Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements" -PassThru -Wait
          
          # Refresh PATH to pick up new installation
          $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
          
          # Re-check
          if (Get-Command py -ErrorAction SilentlyContinue) {
            $basePython = "py -3.12"
          } elseif (Is-PythonCompatible "python") {
            $basePython = "python"
          }
        }
      }
    }

    # Fallback/Error handle
    if (-not $basePython) {
        if (Get-Command python -ErrorAction SilentlyContinue) {
          $basePython = "python" # Use whatever is available as last resort
          Write-Log "WARNING: Using incompatible or unknown Python version: $basePython"
        } else {
          $msg = "Python 3 is required but not installed.`n`n" +
                 "Please download Python 3.12 from:`n" +
                 "https://www.python.org/downloads/`n`n" +
                 "Click OK to open the download page."
          [System.Windows.Forms.MessageBox]::Show($msg, "Python Required", [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Error)
          Start-Process "https://www.python.org/downloads/"
          throw "Python installation required"
        }
    }

    Write-Log "Using $basePython to create venv"
    if ($basePython -like "py -*") {
        $parts = $basePython.Split(" ")
        & py $parts[1] -m venv $venvDir
    } else {
        & $basePython -m venv $venvDir
    }
  }

  if (-not (Test-Path $pythonExe)) {
    throw "Venv creation did not produce $pythonExe"
  }

  # Dependencies will be handled by the UI itself to provide user feedback
  Write-Log "Handing off dependency check to UI"

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
