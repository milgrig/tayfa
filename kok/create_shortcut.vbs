' Create Tayfa Shortcut with Icon
' VBScript to create a Windows shortcut (.lnk) for tayfa.bat
'
' Usage: Double-click to run, or: cscript create_shortcut.vbs

Option Explicit

Dim WshShell, fso, Shortcut
Dim ScriptDir, BatPath, IconPath, ShortcutPath
Dim ShortScriptDir, ShortBatPath, ShortIconPath

' Create objects
Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' Get script directory
ScriptDir = fso.GetParentFolderName(WScript.ScriptFullName)

' Get short path to handle Unicode characters in path
ShortScriptDir = fso.GetFolder(ScriptDir).ShortPath

' Define paths using short names
ShortBatPath = fso.BuildPath(ShortScriptDir, "tayfa.bat")
ShortIconPath = fso.BuildPath(ShortScriptDir, "static\tayfa-icon.ico")
ShortcutPath = fso.BuildPath(ShortScriptDir, "Tayfa.lnk")

' Check for verbose mode
Dim bVerbose
bVerbose = False
If WScript.Arguments.Count > 0 Then
    If WScript.Arguments(0) = "-v" Or WScript.Arguments(0) = "--verbose" Then
        bVerbose = True
    End If
End If

' Verify tayfa.bat exists
If Not fso.FileExists(ShortBatPath) Then
    If bVerbose Then WScript.Echo "ERROR: tayfa.bat not found"
    WScript.Quit 1
End If

' Verify icon exists
If Not fso.FileExists(ShortIconPath) Then
    If bVerbose Then WScript.Echo "ERROR: Icon not found at: " & ShortIconPath
    WScript.Quit 1
End If

' Create shortcut using short paths
Set Shortcut = WshShell.CreateShortcut(ShortcutPath)
Shortcut.TargetPath = ShortBatPath
Shortcut.WorkingDirectory = ShortScriptDir
Shortcut.IconLocation = ShortIconPath & ",0"
Shortcut.Description = "Tayfa Orchestrator"
Shortcut.WindowStyle = 1
Shortcut.Save

' Verify creation
If fso.FileExists(ShortcutPath) Then
    ' Check if running in silent mode (no arguments = silent)
    If WScript.Arguments.Count > 0 Then
        If WScript.Arguments(0) = "-v" Or WScript.Arguments(0) = "--verbose" Then
            WScript.Echo ""
            WScript.Echo "========================================"
            WScript.Echo ""
            WScript.Echo " Shortcut created successfully!"
            WScript.Echo ""
            WScript.Echo " Location: " & ShortcutPath
            WScript.Echo ""
            WScript.Echo "========================================"
            WScript.Echo ""
        End If
    End If
Else
    WScript.Echo "ERROR: Failed to create shortcut"
    WScript.Quit 1
End If

' Clean up
Set Shortcut = Nothing
Set fso = Nothing
Set WshShell = Nothing
