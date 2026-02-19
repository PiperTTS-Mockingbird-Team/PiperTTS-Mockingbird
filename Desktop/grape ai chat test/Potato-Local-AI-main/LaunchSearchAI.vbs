Set FSO = CreateObject("Scripting.FileSystemObject")
Set WshShell = CreateObject("WScript.Shell")

' Get the directory where the script is located
strPath = FSO.GetParentFolderName(WScript.ScriptFullName)

' Set the working directory to the script's folder
WshShell.CurrentDirectory = strPath

' Define the path to the python executable and the script
pythonExe = """" & strPath & "\.venv\Scripts\python.exe"""
scriptPath = """" & strPath & "\gui_app.py"""

' Run the command hidden (0)
WshShell.Run pythonExe & " " & scriptPath, 0, False
