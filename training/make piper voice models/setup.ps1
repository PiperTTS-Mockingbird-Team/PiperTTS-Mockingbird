# setup.ps1: Setup script for TextyMcSpeechy on Windows (PowerShell)

$RUN_CONTAINER_SCRIPT_NAME = "run_container.ps1"

function Informed-Consent {
    Write-Host ""
    Write-Host "This script will do the following things:" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "1. Check for required software (Docker Desktop)"
    Write-Host "2. Create PowerShell versions of run scripts"
    Write-Host "3. Let you choose which type of container you want to use"
    Write-Host "   (prebuilt image from dockerhub vs locally built docker image)"
    Write-Host "4. Check if NVIDIA GPU support is available in Docker"
    Write-Host ""
}

function Check-Docker {
    Write-Host "Checking for Docker..." -NoNewline
    $dockerCheck = Get-Command docker -ErrorAction SilentlyContinue
    if ($dockerCheck) {
        Write-Host " OK! -- Docker is installed." -ForegroundColor Green
        return $true
    } else {
        Write-Host " WARNING -- Docker is not installed." -ForegroundColor Yellow
        Write-Host "Please install Docker Desktop for Windows: https://docs.docker.com/desktop/install/windows-install/"
        return $false
    }
}

function Check-Nvidia-GPU {
    Write-Host "Checking for NVIDIA GPU support in Docker..." -NoNewline
    # Modern Docker on Windows with WSL2 support uses --gpus all
    $gpuCheck = docker run --rm --gpus all alpine nvidia-smi 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host " OK! -- GPU support is functional." -ForegroundColor Green
        return $true
    } else {
        Write-Host " WARNING! -- GPU support failed or not detected." -ForegroundColor Yellow
        Write-Host "Training will be slow on CPU. Ensure you have the latest NVIDIA drivers"
        Write-Host "and Docker Desktop's WSL2 backend is enabled."
        return $false
    }
}

Clear-Host
Informed-Consent

$response = Read-Host "Do you wish to continue? (y/n)"
if ($response -notmatch '^[Yy]$') {
    Write-Host "Exiting..."
    exit
}

$dockerOk = Check-Docker
if (-not $dockerOk) {
    Write-Host "Unable to proceed without Docker."
    exit 1
}

Check-Nvidia-GPU

Write-Host "`nChoose which type of container you want to use:"
Write-Host "1) Prebuilt image (fastest, downloads ~6GB)"
Write-Host "2) Locally built image (builds from Dockerfile, more control)"
$choice = Read-Host "Choice (1 or 2)"

$runContainerContent = @"
# run_container.ps1: Alias to start the docker container
if ('$choice' -eq '1') {
    & ".\prebuilt_container_run.ps1"
} else {
    & ".\local_container_run.ps1"
}
"@

$runContainerContent | Out-File -FilePath $RUN_CONTAINER_SCRIPT_NAME -Encoding utf8

Write-Host "`nSetup complete! You can now use '$RUN_CONTAINER_SCRIPT_NAME' to start the environment." -ForegroundColor Green
Write-Host "You should also check tts_dojo/newdojo.ps1 to create a new training project."
