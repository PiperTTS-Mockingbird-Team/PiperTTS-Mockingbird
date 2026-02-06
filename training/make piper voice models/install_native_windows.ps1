# install_native_windows.ps1: Attempt to install Piper training natively on Windows

$PYTHON_VERSION = "3.10" # Piper training is optimized for 3.10

Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host "WARNING: NATIVE WINDOWS SETUP IS EXPERIMENTAL" -ForegroundColor Yellow
Write-Host "This requires:"
Write-Host "1. Python 3.10 (Specifically 3.10.x)"
Write-Host "2. Microsoft Visual Studio Build Tools with C++ Desktop Development"
Write-Host "3. Git"
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 1. Check Python version
$pythonExe = "py"
$version = & $pythonExe -3.10 --version 2>&1
if ($version -notmatch "3.10") {
    Write-Host "Python 3.10 not found. Attempting to use default 'python'..." -ForegroundColor Yellow
    $pythonExePath = "python"
} else {
    $pythonExePath = "py -3.10"
}

# 2. Create Virtual Environment
Write-Host "`nCreating virtual environment (venv_piper) using $pythonExePath..."
& py -3.10 -m venv venv_piper
if ($LASTEXITCODE -ne 0) { Write-Host "Failed to create venv." -ForegroundColor Red; exit 1 }

$pip = "$PWD\venv_piper\Scripts\pip.exe"
$pythonVenv = "$PWD\venv_piper\Scripts\python.exe"

# 2b. Upgrade pip separately to avoid issues
Write-Host "`nUpgrading pip, wheel, setuptools..."
& $pythonVenv -m pip install --upgrade pip wheel setuptools

# 3. Clone Piper Source (required for training modules)
if (-not (Test-Path "piper_src")) {
    Write-Host "`nCloning Piper source code..."
    git clone https://github.com/rhasspy/piper.git piper_src
    Set-Location piper_src
    git checkout a0f09cdf9155010a45c243bc8a4286b94f286ef4
    Set-Location ..
}

# 4. Install Dependencies
Write-Host "`nInstalling dependencies from requirements_windows.txt..."
& $pip install --upgrade pip wheel setuptools
& $pip install -r requirements_windows.txt

# 5. Build Monotonic Align (CRITICAL C++ STEP)
Write-Host "`nAttempting to build monotonic_align (Requires C++ Build Tools)..."
Set-Location "piper_src\src\python"
& $pythonVenv setup.py develop
Set-Location ..\..\..

Write-Host "`n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
Write-Host "Installation attempt finished." -ForegroundColor Cyan
Write-Host "If you saw red 'error' text above, you likely need to install 'Desktop development with C++'"
Write-Host "via the Visual Studio Installer: https://visualstudio.microsoft.com/visual-cpp-build-tools/"
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
