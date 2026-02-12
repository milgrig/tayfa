# Tayfa Orchestrator — запуск
# Использование: .\tayfa.ps1

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
Write-Host "     Мультиагентная система" -ForegroundColor DarkCyan
Write-Host "     ─────────────────────────────────────" -ForegroundColor DarkGray
Write-Host ""

# Переходим в папку скрипта
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

# ── [1/4] Проверяем Python ───────────────────────────
Write-Host "  [1/4] Проверяю Python..." -ForegroundColor White
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
    Write-Host "  [!] ОШИБКА: Python 3 не найден!" -ForegroundColor Red
    Write-Host "      Установите: https://python.org" -ForegroundColor DarkGray
    exit 1
}
Write-Host ""

# ── [2/4] Виртуальное окружение ──────────────────────
Write-Host "  [2/4] Проверяю виртуальное окружение..." -ForegroundColor White
if (-not (Test-Path ".\venv")) {
    Write-Host "        Создаю venv..." -ForegroundColor Yellow
    & $python -m venv venv
    Write-Host "        Готово." -ForegroundColor Green
} else {
    Write-Host "        venv найден." -ForegroundColor Green
}
Write-Host ""

# ── [3/4] Активируем и ставим зависимости ────────────
& ".\venv\Scripts\Activate.ps1"

Write-Host "  [3/4] Устанавливаю зависимости..." -ForegroundColor White
pip install -q -r requirements.txt 2>&1 | Out-Null
Write-Host "        Готово." -ForegroundColor Green
Write-Host ""

# ── [4/4] Запуск ─────────────────────────────────────
Write-Host "  [4/4] Запускаю Tayfa Orchestrator..." -ForegroundColor White
Write-Host ""
Write-Host "  ┌─────────────────────────────────────────┐" -ForegroundColor DarkCyan
Write-Host "  │                                         │" -ForegroundColor DarkCyan
Write-Host "  │   http://localhost:8000                  │" -ForegroundColor Cyan
Write-Host "  │                                         │" -ForegroundColor DarkCyan
Write-Host "  │   Браузер откроется автоматически.       │" -ForegroundColor DarkCyan
Write-Host "  │   WSL + Claude API запустятся сами.      │" -ForegroundColor DarkCyan
Write-Host "  │                                         │" -ForegroundColor DarkCyan
Write-Host "  │   Ctrl+C — остановить                   │" -ForegroundColor DarkGray
Write-Host "  │                                         │" -ForegroundColor DarkCyan
Write-Host "  └─────────────────────────────────────────┘" -ForegroundColor DarkCyan
Write-Host ""

python app.py

Write-Host ""
Write-Host "  Tayfa остановлен." -ForegroundColor DarkGray
Write-Host ""
