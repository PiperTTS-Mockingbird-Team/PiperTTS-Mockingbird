# new_dojo.ps1: Creates and configures a new dojo for training piper voice models

param (
    # The name of the voice to create, which determines the directory name
    [Parameter(Mandatory=$false, Position=0)]
    [string]$VoiceName,

    # Quality: L, M, H (Default M)
    [Parameter(Mandatory=$false, Position=1)]
    [string]$Quality = "M",

    # Gender: male, female, M, F (Default F)
    [Parameter(Mandatory=$false, Position=2)]
    [string]$Gender = "F",

    # Scratch: true or false (Default false)
    [Parameter(Mandatory=$false, Position=3)]
    [string]$Scratch = "false"
)

# Ensure the script runs relative to its own location to avoid path resolution issues
$PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location -Path $PSScriptRoot

# Validate that a voice name was actually provided
if (-not $VoiceName) {
    Write-Host ""
    Write-Host "Usage: .\new_dojo.ps1 <VOICE_NAME>" -ForegroundColor Yellow
    Write-Host "  Please supply a name for the voice being created."
    Write-Host "  Training environment will be created in tts_dojo\<VOICE_NAME>_dojo"
    Write-Host ""
    exit 1
}

# Optimization: Sanitize voice name to be safe for filenames and shell scripts
# Use the same logic as the Python manager for consistency
$VoiceName = -join ($VoiceName.ToCharArray() | Where-Object { [char]::IsLetterOrDigit($_) -or $_ -eq '-' -or $_ -eq '_' -or [char]::IsWhiteSpace($_) })

# Also prevent double quotes in the name to avoid breaking shell variable assignments
$CleanVoiceName = ($VoiceName -replace '"', '').Trim()

$DojoDir = "tts_dojo"
$TemplateDir = Join-Path $DojoDir "DOJO_CONTENTS"
$DirectoryName = "${CleanVoiceName}_dojo"
$FullPath = Join-Path $DojoDir $DirectoryName

# Check if the template directory exists before proceeding
if (-not (Test-Path $TemplateDir)) {
    Write-Host "Error: Template directory '$TemplateDir' not found." -ForegroundColor Red
    exit 1
}

# Prevent overwriting an existing dojo directory
if (Test-Path $FullPath) {
    Write-Host "Error: Directory '$FullPath' already exists." -ForegroundColor Red
    exit 1
}

# Initialize the root directory for the new voice (using -Force ensures parent creation)
New-Item -ItemType Directory -Path $FullPath -Force | Out-Null

Write-Host ""
Write-Host "Dojo created in : '$FullPath'"
Write-Host "Populating with template contents..."

# Seed the new dojo with standard training scripts and configurations from the template.
# Optimization: Exclude large data folders or binaries from the template copy to keep 
# the new project size minimal (often several GBs of savings).
$excluded = @("archived_*", "training_folder", "voice_checkpoints", "tts_voices", "*.ckpt", "*.onnx")
Copy-Item -Path "$TemplateDir\*" -Destination "$FullPath" -Recurse -Exclude $excluded -ErrorAction Stop

# Fix line endings (CRLF -> LF) for Linux scripts to ensure compatibility with Docker/Linux bash
Write-Host "Sanitizing script line endings..."
# Optimization: Use -File to skip directories and improve filter reliability
Get-ChildItem -Path "$FullPath" -Recurse -File | ForEach-Object {
    $path = $_.FullName
    # Only process specific file types that are sensitive to line endings in Linux/Docker
    if ($_.Extension -match '\.(sh|conf|txt)$' -or $_.Name -match '^\.(QUALITY|SCRATCH|SAMPLING_RATE|MAX_WORKERS)$') {
        # Read text and swap Windows CRLF (\r\n) for Linux LF (\n)
        $content = [System.IO.File]::ReadAllText($path)
        if ($content -match "`r`n") {
            $content = $content -replace "`r`n", "`n"
            # Save explicitly as UTF-8 without BOM, which is standard for Linux scripts
            [System.IO.File]::WriteAllText($path, $content, [System.Text.UTF8Encoding]::new($false))
        }
    }
}

# --------------------------------------------------------------------------------------
# [STEP 2] AUTO-TRAIN FLOW: Dojo Creation & Configuration
#
# This file is called by piper_manager_ui.py to set up the training environment.
#
# 1. Creates `tts_dojo/<voice>_dojo`.
# 2. Copies template scripts (DOJO_CONTENTS/*).
# 3. Sanitizes line endings (Windows CRLF -> Linux LF) so scripts run in Docker.
# 4. Generates `dataset.conf` and marker files (.QUALITY, .SCRATCH) tailored for
#    the "Auto" flow, so the user doesn't have to edit config files manually.
#
# The dojo training scripts run inside Linux (Docker) and `source` dataset.conf.
# If we write with CRLF, bash will often read variables with a trailing `\r`.
# So we write these files with LF line endings explicitly.
#
# The training flow expects:
# - target_voice_dataset/dataset.conf (non-empty)
# - target_voice_dataset/.QUALITY and target_voice_dataset/.SCRATCH
# - scripts/.SAMPLING_RATE and scripts/.MAX_WORKERS
#
# Without these, preprocess/train may fail or prompt unexpectedly.
# --------------------------------------------------------------------------------------

$dojoRoot = $FullPath
$datasetDir = Join-Path $dojoRoot "dataset"
$targetDir  = Join-Path $dojoRoot "target_voice_dataset"
$scriptsDir = Join-Path $dojoRoot "scripts"

New-Item -ItemType Directory -Force -Path $datasetDir  | Out-Null
New-Item -ItemType Directory -Force -Path $targetDir   | Out-Null
New-Item -ItemType Directory -Force -Path $scriptsDir  | Out-Null

# Create essential directories required by the Piper training scripts
# These are initially empty but must exist for the Linux bash scripts to start without errors.
New-Item -ItemType Directory -Force -Path (Join-Path $dojoRoot "voice_checkpoints") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $dojoRoot "tts_voices") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $dojoRoot "archived_checkpoints") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $dojoRoot "archived_tts_voices") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $dojoRoot "training_folder") | Out-Null

# Helper function to write files using Linux-style line endings (LF)
# This is critical because the training container runs on Linux.
function Ensure-FileWithContentLF {
    param(
        [Parameter(Mandatory=$true)][string]$Path,
        [Parameter(Mandatory=$true)][string]$Content
    )

    try {
        # Check if file exists and has content to avoid unnecessary writes
        if (Test-Path $Path) {
            $len = (Get-Item $Path).Length
            if ($len -gt 0) { return }
        }

        # Create parent directories if they don't exist
        $parent = Split-Path -Parent $Path
        if ($parent -and -not (Test-Path $parent)) {
            New-Item -ItemType Directory -Force -Path $parent | Out-Null
        }

        # WriteAllText preserves the exact newline characters in $Content (assumed to be LF).
        # We use UTF8 without a Byte Order Mark (BOM) for Linux compatibility.
        [System.IO.File]::WriteAllText($Path, $Content, [System.Text.UTF8Encoding]::new($false))
    }
    catch {
        Write-Host "Warning: Failed to write $Path - $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

# Hard-coded defaults for a newly created voice.
# Users can change gender, quality, and rate later via the Training Dashboard UI.
$quality_upper = $Quality.ToUpper()
$defaultQualityCode = "M"
if ($quality_upper -eq "L" -or $quality_upper -eq "LOW") { $defaultQualityCode = "L" }
elseif ($quality_upper -eq "H" -or $quality_upper -eq "HIGH") { $defaultQualityCode = "H" }

$defaultScratch = $Scratch.ToLower()

$defaultSampleRate = "22050"
if ($defaultQualityCode -eq "L") { $defaultSampleRate = "16000" }
elseif ($defaultQualityCode -eq "H") { $defaultSampleRate = "44100" }

$defaultMaxWorkers = "4"
$defaultGender = $Gender # Use user provided gender (link_dataset.sh handles M/F/male/female)

# Attempt to load global defaults from the main configuration file
$defaultEspeakLang = "en-us"
$defaultPiperPrefix = "en_US"
try {
    # Path to the main UI config, one directory level up from the script's folder
    $configPath = Join-Path (Split-Path -Parent $PSScriptRoot) "src\config.json"
    if (Test-Path $configPath) {
        $cfg = Get-Content $configPath -Raw | ConvertFrom-Json
        # apply values from JSON if they exist
        if ($cfg.default_espeak_language) { $defaultEspeakLang = [string]$cfg.default_espeak_language }
        if ($cfg.default_piper_filename_prefix) { $defaultPiperPrefix = [string]$cfg.default_piper_filename_prefix }
    }
}
catch {
    # If config.json is missing or invalid, just fall back to hard-coded defaults
}

# Construct the bash-compatible dataset configuration file content.
# This file is sourced by the shell scripts inside the training container.
$datasetConfContent = @"
# Auto-generated by PiperTTS Mockingbird Dashboard
NAME="$CleanVoiceName"
DESCRIPTION="Custom voice"
DEFAULT_VOICE_TYPE="$defaultGender"
LOW_AUDIO="wav_16000"
MEDIUM_AUDIO="wav_22050"
HIGH_AUDIO="wav_44100"
ESPEAK_LANGUAGE_IDENTIFIER="$defaultEspeakLang"
PIPER_FILENAME_PREFIX="$defaultPiperPrefix"
"@

# Fix any Windows line endings in the here-string to ensure Linux compatibility
$datasetConfContent = $datasetConfContent -replace "`r`n", "`n"

# Write config and marker files to appropriate directories inside the new dojo.
# The 'target_voice_dataset' is typically where the user's recorded wavs go.
Ensure-FileWithContentLF -Path (Join-Path $datasetDir "dataset.conf") -Content $datasetConfContent
Ensure-FileWithContentLF -Path (Join-Path $targetDir  "dataset.conf") -Content $datasetConfContent

# Quality marker: Tells piper scripts which quality level (L/M/H) to target
Ensure-FileWithContentLF -Path (Join-Path $datasetDir ".QUALITY") -Content ("$defaultQualityCode`n")
Ensure-FileWithContentLF -Path (Join-Path $targetDir  ".QUALITY") -Content ("$defaultQualityCode`n")

# Scratch marker: Determines if we start from a pre-trained base or from zero
Ensure-FileWithContentLF -Path (Join-Path $datasetDir ".SCRATCH") -Content ("$defaultScratch`n")
Ensure-FileWithContentLF -Path (Join-Path $targetDir  ".SCRATCH") -Content ("$defaultScratch`n")

# Global hardware/training settings markers
Ensure-FileWithContentLF -Path (Join-Path $scriptsDir ".SAMPLING_RATE") -Content ("$defaultSampleRate`n")
Ensure-FileWithContentLF -Path (Join-Path $scriptsDir ".MAX_WORKERS") -Content ("$defaultMaxWorkers`n")

# Inform the user that the dojo is set up and provide the next step
Write-Host ""
Write-Host "  Dojo is ready!" -ForegroundColor Green
Write-Host "  Use '.\run_training.ps1' to start the training session."
Write-Host ""
