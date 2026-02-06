@echo off
:: Batch wrapper to launch the Piper TTS server via PowerShell.
:: This ensures the correct execution policy is set for the PowerShell script.

setlocal
set SCRIPT_DIR=%~dp0
set ROOT_DIR=%SCRIPT_DIR%..

:: Execute the PowerShell startup script
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%start_piper_server.ps1"

endlocal
