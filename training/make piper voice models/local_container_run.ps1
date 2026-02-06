# local_container_run.ps1 - launches a locally built docker container on Windows

# ensure docker files exist.
if (-not (Test-Path "docker-compose.yml")) {
    Write-Host "Error: docker-compose.yml not found!" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path "Dockerfile")) {
    Write-Host "Error: Dockerfile not found!" -ForegroundColor Red
    exit 1
}

Write-Host "Starting Docker container textymcspeechy-piper via Docker Compose..."

# In Windows PowerShell, we don't need to export PUID/PGID as strictly as Linux bash
# but we can pass them in the environment block if needed.
# For Docker Desktop, it's usually safest to let it default or map to 1000:1000
$env:TMS_USER_ID = "1000"
$env:TMS_GROUP_ID = "1000"

docker compose up -d

if ($LASTEXITCODE -eq 0) {
    Write-Host "Container started successfully." -ForegroundColor Green
} else {
    Write-Host "Failed to start container." -ForegroundColor Red
}
