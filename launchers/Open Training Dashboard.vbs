' VBScript launcher to open the Piper Training Dashboard without showing a console window.
On Error Resume Next
Set WshShell = CreateObject("WScript.Shell")
strPath = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))
ps1Path = chr(34) & strPath & "src\tools\open_training_dashboard.ps1" & chr(34)
cmd = "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File " & ps1Path
WshShell.Run cmd, 0, True
