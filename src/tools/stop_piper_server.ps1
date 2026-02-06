# PowerShell script to stop any process listening on the Piper TTS server port (default 5002).

$ErrorActionPreference = 'Stop'

$port = 5002

# Find processes listening on the specified port
$procs = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
  Select-Object -ExpandProperty OwningProcess -Unique

if (-not $procs) {
  Write-Host "No process is listening on port $port."
  exit 0
}

# Forcefully stop each process found
foreach ($processId in $procs) {
  Write-Host "Stopping PID $processId (port $port) ..."
  Stop-Process -Id $processId -Force
}

Write-Host "Stopped."
