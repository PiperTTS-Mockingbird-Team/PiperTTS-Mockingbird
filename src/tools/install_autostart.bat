@echo off
:: Batch script to enable autostart for the Piper TTS server on Windows.
:: It creates a shortcut in the user's Startup folder that points to the startup batch file.

setlocal
set SCRIPT_DIR=%~dp0
set ROOT_DIR=%SCRIPT_DIR%..
set START_BAT=%ROOT_DIR%tools\start_piper_server.bat

set STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
set LINK_PATH=%STARTUP_DIR%\PiperTTS Mockingbird.lnk

:: Create a Startup-folder shortcut using PowerShell (no admin required)
:: WindowStyle = 7 means "Minimized"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$WshShell = New-Object -ComObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%LINK_PATH%'); $Shortcut.TargetPath = '%START_BAT%'; $Shortcut.WorkingDirectory = '%ROOT_DIR%'; $Shortcut.WindowStyle = 7; $Shortcut.Save();" >nul 2>&1

if %ERRORLEVEL% NEQ 0 (
  echo Failed to enable autostart.
  echo Try running this as your normal user.
  exit /b 1
)

echo Enabled autostart (Startup folder shortcut).
echo It will run on next login.

:: Cleanup legacy autostart method (older versions used HKCU Run key)
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "Piper TTS Server" /f >nul 2>&1

endlocal
