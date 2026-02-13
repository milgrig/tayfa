' Create Desktop Shortcut for Tayfa
' Creates Tayfa.lnk that launches the VBS launcher (hidden terminal)

Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")

' Get paths
ScriptDir = FSO.GetParentFolderName(WScript.ScriptFullName)
DesktopPath = WshShell.SpecialFolders("Desktop")

' Shortcut target - VBS launcher (hides terminal)
LauncherPath = ScriptDir & "\tayfa_launcher.vbs"
IconPath = ScriptDir & "\static\tayfa-icon.ico"
LocalShortcut = ScriptDir & "\Tayfa.lnk"

' Create shortcut in the kok folder
Set Shortcut = WshShell.CreateShortcut(LocalShortcut)
Shortcut.TargetPath = LauncherPath
Shortcut.WorkingDirectory = ScriptDir
Shortcut.Description = "Tayfa Orchestrator - Team Management System"
Shortcut.WindowStyle = 1

' Set icon if exists
If FSO.FileExists(IconPath) Then
    Shortcut.IconLocation = IconPath
End If

Shortcut.Save

' Also create shortcut on Desktop
DesktopShortcut = DesktopPath & "\Tayfa.lnk"
Set Shortcut2 = WshShell.CreateShortcut(DesktopShortcut)
Shortcut2.TargetPath = LauncherPath
Shortcut2.WorkingDirectory = ScriptDir
Shortcut2.Description = "Tayfa Orchestrator - Team Management System"
Shortcut2.WindowStyle = 1

If FSO.FileExists(IconPath) Then
    Shortcut2.IconLocation = IconPath
End If

Shortcut2.Save

WScript.Echo "Shortcut created on Desktop!"
