' VBScript launcher to open the PiperTTS Mockingbird without showing a console window.
' This script calls the PowerShell launcher with a hidden window style.

On Error Resume Next

Set WshShell = CreateObject("WScript.Shell")

' Get the directory of the current script
strPath = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))

' Construct the command to run PowerShell directly (hidden) to avoid cmd.exe flashes.
ps1Path = chr(34) & strPath & "src\tools\open_manager_ui.ps1" & chr(34)
cmd = "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File " & ps1Path

' Run the command: 0 = hidden window, True = wait for completion to detect failures
exitCode = WshShell.Run(cmd, 0, True)

' Error handling for the launcher itself
If Err.Number <> 0 Then
	MsgBox "Failed to start PiperTTS Mockingbird (launcher error)." & vbCrLf & vbCrLf & _
				 "Error: " & Err.Description & vbCrLf & _
				 "Try running open_manager_ui.ps1 manually to see output.", vbCritical, "PiperTTS Mockingbird"
ElseIf exitCode <> 0 Then
	' Error handling for the PowerShell script execution
	MsgBox "PiperTTS Mockingbird did not start (PowerShell exited with code " & exitCode & ")." & vbCrLf & vbCrLf & _
				 "Check the log file:" & vbCrLf & strPath & "open_manager_ui.log", vbCritical, "PiperTTS Mockingbird"
End If

Set WshShell = Nothing
