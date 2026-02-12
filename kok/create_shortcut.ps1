<#
.SYNOPSIS
    Create Tayfa Shortcut with Icon

.DESCRIPTION
    PowerShell script to create a Windows shortcut (.lnk) for tayfa.bat
    with custom icon from static/tayfa-icon.ico

    Handles paths with Unicode characters by using short (8.3) paths.

.NOTES
    Usage: Right-click -> Run with PowerShell
           Or: powershell -ExecutionPolicy Bypass -File create_shortcut.ps1
#>

# Get script directory
$ScriptDir = $PSScriptRoot
if (-not $ScriptDir) {
    $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
}
if (-not $ScriptDir) {
    $ScriptDir = (Get-Location).Path
}

Write-Host ""
Write-Host "  Creating Tayfa shortcut..." -ForegroundColor Cyan

# Get short path to handle Unicode characters
$fso = New-Object -ComObject Scripting.FileSystemObject
$ShortScriptDir = $fso.GetFolder($ScriptDir).ShortPath

Write-Host "  Directory: $ShortScriptDir" -ForegroundColor Gray

# Define paths using short names
$BatPath = Join-Path $ShortScriptDir "tayfa.bat"
$IconPath = Join-Path $ShortScriptDir "static\tayfa-icon.ico"
$ShortcutPath = Join-Path $ShortScriptDir "Tayfa.lnk"

# Verify source files exist
if (-not (Test-Path $BatPath)) {
    Write-Host ""
    Write-Host "[ERROR] tayfa.bat not found" -ForegroundColor Red
    Write-Host "Make sure this script is in the same folder as tayfa.bat" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

if (-not (Test-Path $IconPath)) {
    Write-Host ""
    Write-Host "[ERROR] Icon not found" -ForegroundColor Red
    Write-Host "Make sure static\tayfa-icon.ico exists" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

try {
    # Create WScript.Shell COM object
    $WshShell = New-Object -ComObject WScript.Shell

    # Create shortcut
    $Shortcut = $WshShell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = $BatPath
    $Shortcut.WorkingDirectory = $ShortScriptDir
    $Shortcut.IconLocation = "$IconPath,0"
    $Shortcut.Description = "Tayfa Orchestrator"
    $Shortcut.WindowStyle = 1

    # Save shortcut
    $Shortcut.Save()

    # Release COM objects
    [System.Runtime.Interopservices.Marshal]::ReleaseComObject($Shortcut) | Out-Null
    [System.Runtime.Interopservices.Marshal]::ReleaseComObject($WshShell) | Out-Null
    [System.Runtime.Interopservices.Marshal]::ReleaseComObject($fso) | Out-Null

    # Verify creation
    if (Test-Path $ShortcutPath) {
        Write-Host ""
        Write-Host "  ========================================" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "   Shortcut created successfully!" -ForegroundColor Green
        Write-Host ""
        Write-Host "   Location: $ShortcutPath" -ForegroundColor White
        Write-Host "   Target:   tayfa.bat" -ForegroundColor White
        Write-Host "   Icon:     tayfa-icon.ico" -ForegroundColor White
        Write-Host ""
        Write-Host "  ========================================" -ForegroundColor Cyan
        Write-Host ""
    } else {
        throw "Shortcut file was not created"
    }
}
catch {
    Write-Host ""
    Write-Host "[ERROR] Failed to create shortcut: $_" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}
