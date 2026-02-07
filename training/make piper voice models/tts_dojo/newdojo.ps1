# newdojo.ps1: Creates and configures a new dojo for training piper voice models

param (
    [Parameter(Mandatory=$false, Position=0)]
    [string]$VoiceName
)

if (-not $VoiceName) {
    Write-Host ""
    Write-Host "Usage: .\newdojo.ps1 <VOICE_NAME>" -ForegroundColor Yellow
    Write-Host "  Please supply a name for the voice being created."
    Write-Host "  Training environment will be created in <VOICE_NAME>_dojo"
    Write-Host ""
    exit 1
}

$Directory = "${VoiceName}_dojo"

if (Test-Path $Directory) {
    Write-Host "Error: Directory '$Directory' already exists." -ForegroundColor Red
    exit 1
}

New-Item -ItemType Directory -Path $Directory | Out-Null

Write-Host ""
Write-Host "Dojo created in : '$(Get-Location)\$Directory'"
Write-Host "Populating with : '$(Get-Location)\DOJO_CONTENTS'"

# Copy DOJO_CONTENTS
Copy-Item -Path ".\DOJO_CONTENTS\*" -Destination ".\$Directory" -Recurse

Write-Host ""
Write-Host "  Dojo is ready!" -ForegroundColor Green
Write-Host "  Use " -NoNewline
Write-Host "run_training.ps1" -ForegroundColor Yellow -NoNewline
Write-Host " inside your new dojo to guide you through the training process."
Write-Host ""
