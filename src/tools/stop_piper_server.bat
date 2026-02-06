@echo off
:: Batch wrapper to stop the Piper TTS server via PowerShell.

setlocal
set SCRIPT_DIR=%~dp0

:: Execute the PowerShell stop script
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%stop_piper_server.ps1"

endlocal
