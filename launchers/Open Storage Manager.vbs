Set objShell = CreateObject("WScript.Shell")
' Get the directory of the current script
strPath = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))
' Path to the Python executable in the venv
pythonExe = strPath & ".venv\Scripts\python.exe"
' Path to the storage manager script
scriptPath = strPath & "src\storage_manager_ui.py"

' Run the script without a command window
objShell.Run """" & pythonExe & """ """ & scriptPath & """", 0, False
