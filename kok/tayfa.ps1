# Tayfa Orchestrator — startup
# Usage: .\tayfa.ps1

$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "Tayfa Orchestrator"

Write-Host ""
Write-Host "  ████████╗ █████╗ ██╗   ██╗███████╗ █████╗ " -ForegroundColor Cyan
Write-Host "  ╚══██╔══╝██╔══██╗╚██╗ ██╔╝██╔════╝██╔══██╗" -ForegroundColor Cyan
Write-Host "     ██║   ███████║ ╚████╔╝ █████╗  ███████║" -ForegroundColor Cyan
Write-Host "     ██║   ██╔══██║  ╚██╔╝  ██╔══╝  ██╔══██║" -ForegroundColor Cyan
Write-Host "     ██║   ██║  ██║   ██║   ██║     ██║  ██║" -ForegroundColor Cyan
Write-Host "     ╚═╝   ╚═╝  ╚═╝   ╚═╝   ╚═╝     ╚═╝  ╚═╝" -ForegroundColor Cyan
Write-Host ""
Write-Host "     Multi-agent system" -ForegroundColor DarkCyan
Write-Host "     ─────────────────────────────────────" -ForegroundColor DarkGray
Write-Host ""

# Navigate to script directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

# ── [1/5] Checking Python ───────────────────────────
Write-Host "  [1/5] Checking Python..." -ForegroundColor White
$python = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "Python 3") {
            $python = $cmd
            Write-Host "        $ver" -ForegroundColor Green
            break
        }
    } catch {}
}

if (-not $python) {
    Write-Host "  [!] ERROR: Python 3 not found!" -ForegroundColor Red
    Write-Host "      Install from: https://python.org" -ForegroundColor DarkGray
    exit 1
}
Write-Host ""

# ── [2/5] Checking Claude Code ──────────────────────
Write-Host "  [2/5] Checking Claude Code..." -ForegroundColor White
try {
    $claudeVer = claude --version 2>&1
    Write-Host "        $claudeVer" -ForegroundColor Green
} catch {
    Write-Host "  [!] WARNING: Claude Code not found!" -ForegroundColor Yellow
    Write-Host "      Install: npm install -g @anthropic-ai/claude-code" -ForegroundColor DarkGray
    Write-Host "      Or work without API agents." -ForegroundColor DarkGray
}
Write-Host ""

# ── [3/5] Virtual environment ──────────────────────
Write-Host "  [3/5] Checking virtual environment..." -ForegroundColor White
if (-not (Test-Path ".\venv")) {
    Write-Host "        Creating venv..." -ForegroundColor Yellow
    & $python -m venv venv
    Write-Host "        Done." -ForegroundColor Green
} else {
    Write-Host "        venv found." -ForegroundColor Green
}
Write-Host ""

# ── [4/5] Activate and install dependencies ────────────
& ".\venv\Scripts\Activate.ps1"

Write-Host "  [4/5] Installing dependencies..." -ForegroundColor White
pip install -q -r requirements.txt 2>&1 | Out-Null
Write-Host "        Done." -ForegroundColor Green
Write-Host ""

# ── [5/5] Startup ─────────────────────────────────
Write-Host "  [5/5] Starting Tayfa Orchestrator..." -ForegroundColor White
Write-Host ""
Write-Host "  ┌─────────────────────────────────────────┐" -ForegroundColor DarkCyan
Write-Host "  │                                         │" -ForegroundColor DarkCyan
Write-Host "  │   http://localhost:8000                  │" -ForegroundColor Cyan
Write-Host "  │                                         │" -ForegroundColor DarkCyan
Write-Host "  │   Browser will open automatically.       │" -ForegroundColor DarkCyan
Write-Host "  │   Claude API will start automatically.   │" -ForegroundColor DarkCyan
Write-Host "  │                                         │" -ForegroundColor DarkCyan
Write-Host "  │   Ctrl+C — stop                         │" -ForegroundColor DarkGray
Write-Host "  │                                         │" -ForegroundColor DarkCyan
Write-Host "  └─────────────────────────────────────────┘" -ForegroundColor DarkCyan
Write-Host ""

python app.py

Write-Host ""
Write-Host "  Tayfa stopped." -ForegroundColor DarkGray
Write-Host ""
