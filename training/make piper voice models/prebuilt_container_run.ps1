# prebuilt_container_run.ps1 - Launches a prebuilt image of textymcspeechy-piper on Windows

# Improve Unicode rendering (box drawing/checkmarks) and avoid mojibake in captured logs.
try {
    [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
    $OutputEncoding = [System.Text.UTF8Encoding]::new($false)
} catch {}

# Ensure we are running from this script's directory so relative paths work.
$PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location -Path $PSScriptRoot

$AUTOMATIC_ESPEAK_RULE_SCRIPT = "tts_dojo\ESPEAK_RULES\automated_espeak_rules.sh"

# Check Docker
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "CRITICAL -- Docker is not installed." -ForegroundColor Red
    exit 1
}

# Values
$TMS_VOLUME_PATH = "$PWD\tts_dojo"
$CONTAINER_NAME = "textymcspeechy-piper"
$IMAGE_NAME = "domesticatedviking/textymcspeechy-piper"

# Optional: override a single python file inside the container.
# IMPORTANT: do NOT mount the entire piper_train package because the prebuilt image
# contains compiled extensions (e.g. monotonic_align) that would be hidden by the mount.
$PIPER_LIGHTNING_FILE = "$PWD\piper_src\src\python\piper_train\vits\lightning.py"

$HAS_PIPER_LIGHTNING_FILE = Test-Path $PIPER_LIGHTNING_FILE

Write-Host ("-" * 78)
Write-Host "Starting Docker container: $CONTAINER_NAME"
Write-Host "              Using image: $IMAGE_NAME"
Write-Host "          Mounting volume: $TMS_VOLUME_PATH -> /app/tts_dojo"
if ($HAS_PIPER_LIGHTNING_FILE) {
    Write-Host "          Mounting source: $PIPER_LIGHTNING_FILE -> /app/piper/src/python/piper_train/vits/lightning.py" -ForegroundColor Cyan
}
Write-Host "                    Ports: Exposing 6006 for TensorBoard"
Write-Host ("-" * 78)

# Check if image exists
$imageExists = docker image inspect $IMAGE_NAME 2>$null
if (-not $imageExists) {
    Write-Host "Docker image $IMAGE_NAME not found locally. Pulling image..."
    docker pull $IMAGE_NAME
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Failed to pull Docker image $IMAGE_NAME." -ForegroundColor Red
        exit 1
    }
}

# Stop existing if running
docker stop $CONTAINER_NAME 2>$null
docker rm $CONTAINER_NAME 2>$null

# Run the docker container
# On Windows, we prefer --gpus all for WSL2 backend
$dockerArgs = @(
    "run", "--rm", "-d",
    "--name", $CONTAINER_NAME,
    "--hostname", $CONTAINER_NAME,
    "--shm-size=4g",
    "--volume", "${TMS_VOLUME_PATH}:/app/tts_dojo"
)

if ($HAS_PIPER_LIGHTNING_FILE) {
    $dockerArgs += @(
        "--volume",
        "${PIPER_LIGHTNING_FILE}:/app/piper/src/python/piper_train/vits/lightning.py:ro"
    )
}

$dockerArgs += @(
    "--gpus", "all",
    "--env", "NVIDIA_VISIBLE_DEVICES=all",
    "--env", "NVIDIA_DRIVER_CAPABILITIES=compute,utility",
    "--tty",
    "-p", "6006:6006",
    $IMAGE_NAME
)

docker @dockerArgs

if ($LASTEXITCODE -eq 0) {
    Write-Host "Container $CONTAINER_NAME started successfully." -ForegroundColor Green
    Write-Host ("-" * 78)
} else {
    Write-Host "Failed to start the container. It may be that --gpus all is not supported on your setup." -ForegroundColor Yellow
    Write-Host "Retrying without GPU support..."
    $dockerArgsNoGpu = @(
        "run", "--rm", "-d",
        "--name", $CONTAINER_NAME,
        "--hostname", $CONTAINER_NAME,
        "--shm-size=4g",
        "--volume", "${TMS_VOLUME_PATH}:/app/tts_dojo"
    )

    if ($HAS_PIPER_LIGHTNING_FILE) {
        $dockerArgsNoGpu += @(
            "--volume",
            "${PIPER_LIGHTNING_FILE}:/app/piper/src/python/piper_train/vits/lightning.py:ro"
        )
    }

    $dockerArgsNoGpu += @(
        "--tty",
        "-p", "6006:6006",
        $IMAGE_NAME
    )

    docker @dockerArgsNoGpu
}
