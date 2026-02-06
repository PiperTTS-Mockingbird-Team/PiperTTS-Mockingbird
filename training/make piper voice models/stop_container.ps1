# stop_container.ps1 - Shut down the textymcspeechy-piper container

param(
    [switch]$DeepCleanup = $false
)

$CONTAINER_NAME = "textymcspeechy-piper"

Write-Host "Stopping Docker container: $CONTAINER_NAME..."
docker stop $CONTAINER_NAME

if ($LASTEXITCODE -eq 0) {
    Write-Host "Container stopped successfully."
} else {
    Write-Host "Container was not running or failed to stop."
}

if ($DeepCleanup) {
    Write-Host "Performing Deep Cleanup to reclaim memory (VmmemWSL)..."
    
    # 1. Prune unused docker resources
    Write-Host "Pruning Docker resources..."
    docker system prune -f
    
    # 2. Kill Docker Desktop processes to prevent auto-restart of WSL
    if ($IsWindows -or $env:OS -eq "Windows_NT") {
        Write-Host "Shutting down Docker Desktop..."
        
        # Kill Docker Desktop GUI
        $dockerDesktop = Get-Process "Docker Desktop" -ErrorAction SilentlyContinue
        if ($dockerDesktop) {
            Stop-Process -Name "Docker Desktop" -Force -ErrorAction SilentlyContinue
            Write-Host "  - Docker Desktop.exe stopped"
        }
        
        # Kill Docker backend engine
        $dockerBackend = Get-Process "com.docker.backend" -ErrorAction SilentlyContinue
        if ($dockerBackend) {
            Stop-Process -Name "com.docker.backend" -Force -ErrorAction SilentlyContinue
            Write-Host "  - Docker backend stopped"
        }
        
        # Give processes a moment to fully terminate
        Start-Sleep -Seconds 2
        
        # 3. Shut down WSL to completely kill the VmmemWSL process memory hog
        Write-Host "Shutting down WSL... This will free up all VmmemWSL memory."
        wsl.exe --shutdown
        
        Write-Host "Deep Cleanup complete! VmmemWSL memory has been released." -ForegroundColor Green
        Write-Host "Note: Docker will automatically restart when you start training again." -ForegroundColor Cyan
    }
}
