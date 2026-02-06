# run_training.ps1: Start a training session for a specific dojo on Windows

param (
    [Parameter(Mandatory=$false)]
    [string]$SelectedDojo,

    [Parameter(Mandatory=$false)]
    [switch]$Auto,

    # In AUTO mode, interactive prompts inside docker exec are unreliable.
    # Use: resume | pretrained | scratch
    [Parameter(Mandatory=$false)]
    [ValidateSet('resume','pretrained','scratch')]
    [string]$StartMode,

    [Parameter(Mandatory=$false)]
    [switch]$PreprocessOnly
)

# Improve Unicode rendering of dojo UI (box drawing / checkmarks) and avoid mojibake.
try {
    [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
    $OutputEncoding = [System.Text.UTF8Encoding]::new($false)
} catch {}

# Ensure we are in the script's directory
$PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location -Path $PSScriptRoot

$CONTAINER_NAME = "textymcspeechy-piper"


# 1. Ensure container is running
if (-not (docker ps -f "name=$CONTAINER_NAME" --format '{{.Names}}')) {
    Write-Host "Container is not running. Initiating Docker management..." -ForegroundColor Cyan
    if (Test-Path ".\manage_docker.ps1") {
        & ".\manage_docker.ps1"
    } else {
        Write-Host "Error: manage_docker.ps1 not found in $PWD" -ForegroundColor Red
        exit 1
    }
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "`nFailed to start or install Docker." -ForegroundColor Red
        exit 1
    }
}

# 2. List available dojos
$dojos = Get-ChildItem -Path ".\tts_dojo" -Directory | Where-Object { $_.Name -like "*_dojo" } | Select-Object -ExpandProperty Name

if ($dojos.Count -eq 0) {
    Write-Host "No dojos found in .\tts_dojo\. Use '.\new_dojo.ps1 <voice_name>' to create one." -ForegroundColor Yellow
    exit 1
}

if (-not $SelectedDojo) {
    Write-Host "`nAvailable Training Dojos:" -ForegroundColor Green
    for ($i=0; $i -lt $dojos.Count; $i++) {
        Write-Host "$($i+1)) $($dojos[$i])"
    }

    $choice = Read-Host "`nSelect a dojo to train (1-$($dojos.Count))"
    $index = [int]$choice - 1

    if ($index -lt 0 -or $index -ge $dojos.Count) {
        Write-Host "Invalid selection." -ForegroundColor Red
        exit 1
    }

    $SelectedDojo = $dojos[$index]
} else {
    Write-Host "Auto-selecting Dojo: $SelectedDojo" -ForegroundColor Cyan
}

Write-Host "Starting training session for $SelectedDojo..." -ForegroundColor Green
if ($Auto) { Write-Host "Running in AUTO mode." -ForegroundColor Cyan }
Write-Host "This will open a bash shell INSIDE the docker container."
Write-Host "Once inside, run: bash run_training.sh" -ForegroundColor Yellow
Write-Host ("-" * 78)

# Join the container and go to the dojo directory
# Path inside container is /app/tts_dojo/<dojo_name>
$autoFlags = @()
if ($Auto) { $autoFlags += "--auto" }
if ($PreprocessOnly) { $autoFlags += "--preprocess-only" }
$autoFlagStr = $autoFlags -join " "

$dockerFlags = if ($Auto) { "-i" } else { "-it" }

# Set TERM environment variable for the process to avoid 'TERM not set' errors
$env:TERM = "xterm"

$modeExport = ""
if ($StartMode) {
    # Passed through to scripts/train.sh in the container
    $modeExport = "export DOJO_START_MODE=$StartMode; "
}

docker exec $dockerFlags $CONTAINER_NAME bash -c "$modeExport export TERM=xterm; cd '/app/tts_dojo/$SelectedDojo' && bash run_training.sh $autoFlagStr" 2>&1
