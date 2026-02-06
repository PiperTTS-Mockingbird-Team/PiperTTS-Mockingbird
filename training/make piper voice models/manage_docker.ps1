# manage_docker.ps1: Ensures Docker is installed, running, and starts the training container.

# Improve Unicode rendering (box drawing/checkmarks) and avoid mojibake in logs.
try {
    [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
    $OutputEncoding = [System.Text.UTF8Encoding]::new($false)
} catch {}

# 1. Check if Docker is installed
$dockerPath = Get-Command docker -ErrorAction SilentlyContinue
if (-not $dockerPath) {
    Write-Host "Docker is not installed. Attempting to install via winget..." -ForegroundColor Yellow
    
    # Try using winget - this will likely prompt for UAC elevation
    Write-Host "This will open a Windows prompt to authorize the installation of Docker Desktop." -ForegroundColor Cyan
    Start-Process -FilePath "winget" -ArgumentList "install Docker.DockerDesktop --accept-package-agreements --accept-source-agreements" -Wait
    
    # Re-check
    $dockerPath = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $dockerPath) {
        Write-Host "Docker installation failed or requires a system restart." -ForegroundColor Red
        Write-Host "Please install Docker Desktop manually from: https://www.docker.com/products/docker-desktop/"
        Read-Host "Press Enter to exit..."
        exit 1
    }
}

# 2. Check if Docker is running
Write-Host "Checking if Docker engine is running..." -NoNewline
docker info >$null 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host " FAILED" -ForegroundColor Red
    Write-Host "Attempting to start Docker Desktop silently..." -ForegroundColor Cyan
    
    $dockerExe = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    if (Test-Path $dockerExe) {
        # Start Docker Desktop and wait for it to become responsive
        Start-Process $dockerExe
        
        $retryCount = 0
        $maxRetries = 30 # Wait up to 5 minutes (10s intervals)
        
        while ($retryCount -lt $maxRetries) {
            Write-Host "." -NoNewline
            docker info >$null 2>$null
            if ($LASTEXITCODE -eq 0) {
                Write-Host " STARTED!" -ForegroundColor Green
                break
            }
            $retryCount++
            Start-Sleep -Seconds 10
        }
        
        if ($retryCount -eq $maxRetries) {
            Write-Host "`nDocker is taking too long to start. Please check the Docker icon in your system tray." -ForegroundColor Yellow
            Read-Host "Press Enter to try continuing anyway..."
        }
    } else {
        Write-Host "Docker Desktop executable not found at $dockerExe." -ForegroundColor Red
        Write-Host "Please start Docker manually."
        Read-Host "Press Enter to exit..."
        exit 1
    }
} else {
    Write-Host " OK!" -ForegroundColor Green
}

# 3. Finally, launch the container
Write-Host "Launching training environment..." -ForegroundColor Cyan
& ".\prebuilt_container_run.ps1"
