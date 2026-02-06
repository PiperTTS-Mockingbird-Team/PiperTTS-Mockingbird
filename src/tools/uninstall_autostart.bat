@echo off
:: Batch script to disable autostart for the Piper TTS server on Windows.
:: It removes the shortcut from the user's Startup folder and cleans up legacy registry entries.

setlocal

set STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
set LINK_PATH=%STARTUP_DIR%\PiperTTS Mockingbird.lnk

:: Remove the Startup folder shortcut if it exists
if exist "%LINK_PATH%" del /f /q "%LINK_PATH%" >nul 2>&1

:: Cleanup legacy autostart method (older versions used HKCU Run key)
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "Piper TTS Server" /f >nul 2>&1

:: Verify removal
if exist "%LINK_PATH%" (
  echo Failed to disable autostart: shortcut could not be removed.
  exit /b 1
)

echo Disabled autostart.

endlocal
