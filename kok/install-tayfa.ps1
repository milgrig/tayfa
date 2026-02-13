<#
.SYNOPSIS
    Установщик Tayfa для Windows

.DESCRIPTION
    Автоматизирует установку всех зависимостей Tayfa:
    - Python 3.10+ (Windows)
    - WSL с Ubuntu
    - Node.js + npm (WSL)
    - Claude Code CLI (WSL)
    - Python venv в WSL и Windows

.PARAMETER Force
    Установить всё без интерактивных вопросов

.PARAMETER SkipOptional
    Пропустить опциональные компоненты (GitHub CLI)

.PARAMETER CheckOnly
    Только проверка, без установки

.EXAMPLE
    .\install-tayfa.ps1
    .\install-tayfa.ps1 -Force
    .\install-tayfa.ps1 -CheckOnly
#>

[CmdletBinding()]
param(
    [switch]$Force,
    [switch]$SkipOptional,
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"
$script:TotalSteps = 8
$script:CurrentStep = 0
$script:Results = @{}

# ============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================================

function Write-Banner {
    $banner = @"

  ████████╗ █████╗ ██╗   ██╗███████╗ █████╗
  ╚══██╔══╝██╔══██╗╚██╗ ██╔╝██╔════╝██╔══██╗
     ██║   ███████║ ╚████╔╝ █████╗  ███████║
     ██║   ██╔══██║  ╚██╔╝  ██╔══╝  ██╔══██║
     ██║   ██║  ██║   ██║   ██║     ██║  ██║
     ╚═╝   ╚═╝  ╚═╝   ╚═╝   ╚═╝     ╚═╝  ╚═╝

         Установщик для Windows

"@
    Write-Host $banner -ForegroundColor Cyan
}

function Write-Step {
    param([string]$Message)
    $script:CurrentStep++
    Write-Host ""
    Write-Host "[$script:CurrentStep/$script:TotalSteps] " -ForegroundColor White -NoNewline
    Write-Host $Message -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "  [✓] " -ForegroundColor Green -NoNewline
    Write-Host $Message -ForegroundColor White
}

function Write-Warning {
    param([string]$Message)
    Write-Host "  [!] " -ForegroundColor Yellow -NoNewline
    Write-Host $Message -ForegroundColor White
}

function Write-Error2 {
    param([string]$Message)
    Write-Host "  [✗] " -ForegroundColor Red -NoNewline
    Write-Host $Message -ForegroundColor White
}

function Write-Info {
    param([string]$Message)
    Write-Host "      " -NoNewline
    Write-Host $Message -ForegroundColor Gray
}

function Write-Action {
    param([string]$Message)
    Write-Host "  [⚡] " -ForegroundColor Magenta -NoNewline
    Write-Host $Message -ForegroundColor White
}

function Test-Admin {
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($currentUser)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Ask-UserConfirm {
    param([string]$Question)

    if ($Force) { return $true }
    if ($CheckOnly) { return $false }

    Write-Host ""
    Write-Host "  $Question " -ForegroundColor Yellow -NoNewline
    Write-Host "(y/n): " -NoNewline
    $response = Read-Host
    return ($response -eq 'y' -or $response -eq 'Y' -or $response -eq 'да' -or $response -eq 'Да')
}

function Test-CommandExists {
    param([string]$Command)
    $oldPreference = $ErrorActionPreference
    $ErrorActionPreference = 'SilentlyContinue'
    try {
        if (Get-Command $Command) { return $true }
    } catch {}
    $ErrorActionPreference = $oldPreference
    return $false
}

function Invoke-WslCommand {
    param([string]$Command)
    $result = wsl -e bash -c $Command 2>&1
    return $result
}

function Test-WslCommandExists {
    param([string]$Command)
    $result = wsl -e which $Command 2>&1
    return ($LASTEXITCODE -eq 0)
}

# ============================================================================
# ШАГ 1: ПРОВЕРКА PYTHON НА WINDOWS
# ============================================================================

function Step-CheckPython {
    Write-Step "Проверяю Python на Windows..."

    $pythonCmd = $null
    $pythonVersion = $null

    # Проверяем python
    if (Test-CommandExists "python") {
        $versionOutput = python --version 2>&1
        if ($versionOutput -match "Python (\d+\.\d+\.\d+)") {
            $pythonVersion = $Matches[1]
            $pythonCmd = "python"
        }
    }

    # Проверяем py launcher
    if (-not $pythonCmd -and (Test-CommandExists "py")) {
        $versionOutput = py --version 2>&1
        if ($versionOutput -match "Python (\d+\.\d+\.\d+)") {
            $pythonVersion = $Matches[1]
            $pythonCmd = "py"
        }
    }

    if ($pythonCmd) {
        # Проверяем версию >= 3.10
        $versionParts = $pythonVersion.Split('.')
        $major = [int]$versionParts[0]
        $minor = [int]$versionParts[1]

        if ($major -ge 3 -and $minor -ge 10) {
            Write-Success "Python $pythonVersion найден ($pythonCmd)"
            $script:Results["Python"] = @{Status = "OK"; Version = $pythonVersion; Command = $pythonCmd}
            return $true
        } else {
            Write-Warning "Python $pythonVersion найден, но требуется 3.10+"
        }
    }

    Write-Error2 "Python 3.10+ не найден"
    Write-Info "Скачайте Python: https://python.org/downloads/"
    Write-Info "ВАЖНО: При установке отметьте 'Add Python to PATH'"
    $script:Results["Python"] = @{Status = "MISSING"; Version = $null}
    return $false
}

# ============================================================================
# ШАГ 2: ПРОВЕРКА WSL
# ============================================================================

function Step-CheckWSL {
    Write-Step "Проверяю WSL..."

    # Проверяем, установлен ли WSL
    try {
        $wslStatus = wsl --status 2>&1
        if ($LASTEXITCODE -ne 0) {
            throw "WSL не установлен"
        }
    } catch {
        Write-Error2 "WSL не установлен"

        if (-not (Test-Admin)) {
            Write-Warning "Для установки WSL требуются права администратора"
            Write-Info "Запустите PowerShell от администратора и выполните:"
            Write-Info "  wsl --install"
            $script:Results["WSL"] = @{Status = "NEED_ADMIN"}
            return $false
        }

        if (Ask-UserConfirm "Установить WSL?") {
            Write-Action "Устанавливаю WSL..."
            wsl --install --no-launch
            if ($LASTEXITCODE -eq 0) {
                Write-Warning "WSL установлен. Требуется перезагрузка!"
                Write-Info "После перезагрузки запустите этот скрипт снова."
                $script:Results["WSL"] = @{Status = "REBOOT_REQUIRED"}
                return $false
            } else {
                Write-Error2 "Ошибка установки WSL"
                $script:Results["WSL"] = @{Status = "ERROR"}
                return $false
            }
        } else {
            $script:Results["WSL"] = @{Status = "SKIPPED"}
            return $false
        }
    }

    # WSL установлен, проверяем версию
    if ($wslStatus -match "WSL версии:\s*(\d+\.\d+)" -or $wslStatus -match "WSL version:\s*(\d+\.\d+)") {
        $wslVersion = $Matches[1]
        Write-Success "WSL $wslVersion установлен"
        $script:Results["WSL"] = @{Status = "OK"; Version = $wslVersion}
        return $true
    } else {
        Write-Success "WSL установлен"
        $script:Results["WSL"] = @{Status = "OK"; Version = "2"}
        return $true
    }
}

# ============================================================================
# ШАГ 3: ПРОВЕРКА UBUNTU В WSL
# ============================================================================

function Step-CheckUbuntu {
    Write-Step "Проверяю дистрибутив Ubuntu в WSL..."

    # Получаем список дистрибутивов
    $distros = wsl -l -q 2>&1

    if ($distros -match "Ubuntu") {
        # Проверяем версию Ubuntu
        $osRelease = Invoke-WslCommand "cat /etc/os-release 2>/dev/null | grep PRETTY_NAME"
        if ($osRelease -match 'PRETTY_NAME="([^"]+)"') {
            $ubuntuVersion = $Matches[1]
            Write-Success "$ubuntuVersion"
            $script:Results["Ubuntu"] = @{Status = "OK"; Version = $ubuntuVersion}
            return $true
        } else {
            Write-Success "Ubuntu найден"
            $script:Results["Ubuntu"] = @{Status = "OK"; Version = "Unknown"}
            return $true
        }
    }

    Write-Error2 "Ubuntu не найден в WSL"

    if (Ask-UserConfirm "Установить Ubuntu?") {
        Write-Action "Устанавливаю Ubuntu..."
        wsl --install -d Ubuntu --no-launch
        if ($LASTEXITCODE -eq 0) {
            Write-Success "Ubuntu установлен"
            Write-Warning "Запустите Ubuntu из меню Пуск для первоначальной настройки"
            $script:Results["Ubuntu"] = @{Status = "INSTALLED"; Version = "Ubuntu"}
            return $true
        } else {
            Write-Error2 "Ошибка установки Ubuntu"
            $script:Results["Ubuntu"] = @{Status = "ERROR"}
            return $false
        }
    } else {
        $script:Results["Ubuntu"] = @{Status = "SKIPPED"}
        return $false
    }
}

# ============================================================================
# ШАГ 4: ПРОВЕРКА NODE.JS В WSL
# ============================================================================

function Step-CheckNodeJS {
    Write-Step "Проверяю Node.js в WSL..."

    if (Test-WslCommandExists "node") {
        $nodeVersion = Invoke-WslCommand "node --version"
        if ($nodeVersion -match "v(\d+)\.") {
            $majorVersion = [int]$Matches[1]
            if ($majorVersion -ge 18) {
                Write-Success "Node.js $nodeVersion"
                $script:Results["NodeJS"] = @{Status = "OK"; Version = $nodeVersion}
                return $true
            } else {
                Write-Warning "Node.js $nodeVersion найден, но требуется v18+"
            }
        }
    }

    Write-Error2 "Node.js 18+ не найден в WSL"

    if ($CheckOnly) {
        $script:Results["NodeJS"] = @{Status = "MISSING"}
        return $false
    }

    if (Ask-UserConfirm "Установить Node.js 20 LTS в WSL?") {
        Write-Action "Устанавливаю Node.js 20..."

        # Используем NodeSource для установки Node.js 20
        $installScript = @"
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt-get install -y nodejs
"@
        wsl -e bash -c $installScript

        if ($LASTEXITCODE -eq 0) {
            $nodeVersion = Invoke-WslCommand "node --version"
            Write-Success "Node.js $nodeVersion установлен"
            $script:Results["NodeJS"] = @{Status = "OK"; Version = $nodeVersion}
            return $true
        } else {
            Write-Error2 "Ошибка установки Node.js"
            Write-Info "Попробуйте выполнить вручную в WSL:"
            Write-Info "  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -"
            Write-Info "  sudo apt-get install -y nodejs"
            $script:Results["NodeJS"] = @{Status = "ERROR"}
            return $false
        }
    } else {
        $script:Results["NodeJS"] = @{Status = "SKIPPED"}
        return $false
    }
}

# ============================================================================
# ШАГ 5: ПРОВЕРКА CLAUDE CLI В WSL
# ============================================================================

function Step-CheckClaudeCLI {
    Write-Step "Проверяю Claude Code CLI в WSL..."

    if (Test-WslCommandExists "claude") {
        $claudeVersion = Invoke-WslCommand "claude --version 2>/dev/null | head -1"
        Write-Success "Claude CLI: $claudeVersion"
        $script:Results["ClaudeCLI"] = @{Status = "OK"; Version = $claudeVersion}
        return $true
    }

    Write-Error2 "Claude Code CLI не найден в WSL"

    if ($CheckOnly) {
        $script:Results["ClaudeCLI"] = @{Status = "MISSING"}
        return $false
    }

    # Проверяем, что npm доступен
    if (-not (Test-WslCommandExists "npm")) {
        Write-Warning "npm не найден. Сначала установите Node.js"
        $script:Results["ClaudeCLI"] = @{Status = "NEED_NPM"}
        return $false
    }

    if (Ask-UserConfirm "Установить Claude Code CLI?") {
        Write-Action "Устанавливаю Claude Code CLI..."

        wsl -e bash -c "npm install -g @anthropic-ai/claude-code"

        if ($LASTEXITCODE -eq 0) {
            $claudeVersion = Invoke-WslCommand "claude --version 2>/dev/null | head -1"
            Write-Success "Claude CLI установлен: $claudeVersion"
            $script:Results["ClaudeCLI"] = @{Status = "OK"; Version = $claudeVersion}
            return $true
        } else {
            Write-Error2 "Ошибка установки Claude CLI"
            Write-Info "Попробуйте выполнить вручную в WSL:"
            Write-Info "  npm install -g @anthropic-ai/claude-code"
            $script:Results["ClaudeCLI"] = @{Status = "ERROR"}
            return $false
        }
    } else {
        $script:Results["ClaudeCLI"] = @{Status = "SKIPPED"}
        return $false
    }
}

# ============================================================================
# ШАГ 6: СОЗДАНИЕ PYTHON VENV В WSL
# ============================================================================

function Step-SetupWslVenv {
    Write-Step "Проверяю Python venv в WSL (~/claude_venv)..."

    $venvExists = Invoke-WslCommand "test -d ~/claude_venv && echo 'exists'"

    if ($venvExists -match "exists") {
        # Проверяем, что venv рабочий
        $pipCheck = Invoke-WslCommand "~/claude_venv/bin/pip --version 2>/dev/null"
        if ($LASTEXITCODE -eq 0) {
            Write-Success "~/claude_venv существует и работает"
            $script:Results["WslVenv"] = @{Status = "OK"}
            return $true
        } else {
            Write-Warning "~/claude_venv повреждён, пересоздаю..."
        }
    }

    if ($CheckOnly) {
        Write-Error2 "~/claude_venv не найден"
        $script:Results["WslVenv"] = @{Status = "MISSING"}
        return $false
    }

    Write-Action "Создаю ~/claude_venv в WSL..."

    $setupScript = @"
python3 -m venv ~/claude_venv && \
source ~/claude_venv/bin/activate && \
pip install --upgrade pip && \
pip install fastapi uvicorn pydantic
"@

    wsl -e bash -c $setupScript

    if ($LASTEXITCODE -eq 0) {
        Write-Success "~/claude_venv создан с fastapi, uvicorn, pydantic"
        $script:Results["WslVenv"] = @{Status = "OK"}
        return $true
    } else {
        Write-Error2 "Ошибка создания venv в WSL"
        $script:Results["WslVenv"] = @{Status = "ERROR"}
        return $false
    }
}

# ============================================================================
# ШАГ 7: СОЗДАНИЕ PYTHON VENV НА WINDOWS
# ============================================================================

function Step-SetupWindowsVenv {
    Write-Step "Проверяю Python venv на Windows (kok/venv)..."

    $scriptDir = Split-Path -Parent $MyInvocation.ScriptName
    if (-not $scriptDir) { $scriptDir = Get-Location }
    $venvPath = Join-Path $scriptDir "venv"
    $requirementsPath = Join-Path $scriptDir "requirements.txt"

    if (Test-Path (Join-Path $venvPath "Scripts\pip.exe")) {
        Write-Success "kok/venv существует"
        $script:Results["WindowsVenv"] = @{Status = "OK"}

        # Проверяем зависимости
        if (Test-Path $requirementsPath) {
            Write-Info "Проверяю зависимости..."
            try {
                $ErrorActionPreference = "SilentlyContinue"
                $null = & "$venvPath\Scripts\pip.exe" install -q -r $requirementsPath 2>&1
                $ErrorActionPreference = "Stop"
                Write-Success "Зависимости актуальны"
            } catch {
                Write-Warning "Проблема с зависимостями (не критично)"
            }
        }
        return $true
    }

    if ($CheckOnly) {
        Write-Error2 "kok/venv не найден"
        $script:Results["WindowsVenv"] = @{Status = "MISSING"}
        return $false
    }

    # Проверяем Python
    if (-not $script:Results["Python"] -or $script:Results["Python"].Status -ne "OK") {
        Write-Warning "Python не найден, пропускаю создание venv"
        $script:Results["WindowsVenv"] = @{Status = "NEED_PYTHON"}
        return $false
    }

    $pythonCmd = $script:Results["Python"].Command

    Write-Action "Создаю kok/venv..."

    & $pythonCmd -m venv $venvPath

    if ($LASTEXITCODE -eq 0 -and (Test-Path (Join-Path $venvPath "Scripts\pip.exe"))) {
        Write-Success "venv создан"

        # Устанавливаем зависимости
        if (Test-Path $requirementsPath) {
            Write-Action "Устанавливаю зависимости из requirements.txt..."
            $null = & "$venvPath\Scripts\pip.exe" install --upgrade pip 2>&1
            $pipOutput = & "$venvPath\Scripts\pip.exe" install -r $requirementsPath 2>&1
            $pipExitCode = $LASTEXITCODE

            if ($pipExitCode -eq 0) {
                Write-Success "Зависимости установлены"
            } else {
                Write-Warning "Некоторые зависимости не установились"
                Write-Info ($pipOutput | Select-Object -Last 3 | Out-String)
            }
        }

        $script:Results["WindowsVenv"] = @{Status = "OK"}
        return $true
    } else {
        Write-Error2 "Ошибка создания venv"
        $script:Results["WindowsVenv"] = @{Status = "ERROR"}
        return $false
    }
}

# ============================================================================
# ШАГ 8: GITHUB CLI (ОПЦИОНАЛЬНО)
# ============================================================================

function Step-CheckGitHubCLI {
    Write-Step "Проверяю GitHub CLI в WSL (опционально)..."

    if ($SkipOptional) {
        Write-Info "Пропущено (--SkipOptional)"
        $script:Results["GitHubCLI"] = @{Status = "SKIPPED"}
        return $true
    }

    if (Test-WslCommandExists "gh") {
        $ghVersion = Invoke-WslCommand "gh --version | head -1"
        Write-Success "GitHub CLI: $ghVersion"
        $script:Results["GitHubCLI"] = @{Status = "OK"; Version = $ghVersion}
        return $true
    }

    Write-Warning "GitHub CLI не найден (опционально, для git-интеграции)"

    if ($CheckOnly) {
        $script:Results["GitHubCLI"] = @{Status = "MISSING"}
        return $true
    }

    if (Ask-UserConfirm "Установить GitHub CLI?") {
        Write-Action "Устанавливаю GitHub CLI..."

        $installScript = @"
type -p curl >/dev/null || (sudo apt update && sudo apt install curl -y)
curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg
sudo chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg
echo "deb [arch=\$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
sudo apt update
sudo apt install gh -y
"@
        wsl -e bash -c $installScript

        if ($LASTEXITCODE -eq 0) {
            $ghVersion = Invoke-WslCommand "gh --version | head -1"
            Write-Success "GitHub CLI установлен: $ghVersion"
            $script:Results["GitHubCLI"] = @{Status = "OK"; Version = $ghVersion}
        } else {
            Write-Warning "Не удалось установить GitHub CLI"
            $script:Results["GitHubCLI"] = @{Status = "ERROR"}
        }
    } else {
        $script:Results["GitHubCLI"] = @{Status = "SKIPPED"}
    }

    return $true
}

# ============================================================================
# ИТОГОВЫЙ ОТЧЁТ
# ============================================================================

function Write-Summary {
    Write-Host ""
    Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Cyan

    $allOk = $true
    $needReboot = $false
    $needAction = @()

    foreach ($key in @("Python", "WSL", "Ubuntu", "NodeJS", "ClaudeCLI", "WslVenv", "WindowsVenv", "GitHubCLI")) {
        $result = $script:Results[$key]
        if (-not $result) { continue }

        $displayName = switch ($key) {
            "Python" { "Python (Windows)" }
            "WSL" { "WSL" }
            "Ubuntu" { "Ubuntu (WSL)" }
            "NodeJS" { "Node.js (WSL)" }
            "ClaudeCLI" { "Claude CLI (WSL)" }
            "WslVenv" { "claude_venv (WSL)" }
            "WindowsVenv" { "kok/venv (Windows)" }
            "GitHubCLI" { "GitHub CLI (WSL)" }
        }

        switch ($result.Status) {
            "OK" {
                $version = if ($result.Version) { " ($($result.Version))" } else { "" }
                Write-Host "  ✓ " -ForegroundColor Green -NoNewline
                Write-Host "$displayName$version" -ForegroundColor White
            }
            "INSTALLED" {
                Write-Host "  ✓ " -ForegroundColor Green -NoNewline
                Write-Host "$displayName (установлен)" -ForegroundColor White
            }
            "MISSING" {
                Write-Host "  ✗ " -ForegroundColor Red -NoNewline
                Write-Host "$displayName — не найден" -ForegroundColor White
                $allOk = $false
                $needAction += $displayName
            }
            "SKIPPED" {
                Write-Host "  - " -ForegroundColor Gray -NoNewline
                Write-Host "$displayName — пропущен" -ForegroundColor Gray
            }
            "REBOOT_REQUIRED" {
                Write-Host "  ! " -ForegroundColor Yellow -NoNewline
                Write-Host "$displayName — требуется перезагрузка" -ForegroundColor Yellow
                $needReboot = $true
            }
            "NEED_ADMIN" {
                Write-Host "  ! " -ForegroundColor Yellow -NoNewline
                Write-Host "$displayName — требуются права администратора" -ForegroundColor Yellow
                $allOk = $false
            }
            "ERROR" {
                Write-Host "  ✗ " -ForegroundColor Red -NoNewline
                Write-Host "$displayName — ошибка установки" -ForegroundColor Red
                $allOk = $false
            }
            default {
                Write-Host "  ? " -ForegroundColor Gray -NoNewline
                Write-Host "$displayName — $($result.Status)" -ForegroundColor Gray
            }
        }
    }

    Write-Host ""
    Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Cyan

    if ($needReboot) {
        Write-Host ""
        Write-Host "  ⚠ ТРЕБУЕТСЯ ПЕРЕЗАГРУЗКА" -ForegroundColor Yellow
        Write-Host "    После перезагрузки запустите скрипт снова." -ForegroundColor White
        Write-Host ""
        exit 3010
    }

    if ($allOk) {
        Write-Host ""
        Write-Host "  ✓ Tayfa готова к работе!" -ForegroundColor Green
        Write-Host ""
        Write-Host "  Следующий шаг:" -ForegroundColor White
        Write-Host "    cd kok" -ForegroundColor Cyan
        Write-Host "    .\tayfa.bat" -ForegroundColor Cyan
        Write-Host ""
    } else {
        Write-Host ""
        Write-Host "  ⚠ Требуется установить:" -ForegroundColor Yellow
        foreach ($item in $needAction) {
            Write-Host "    - $item" -ForegroundColor White
        }
        Write-Host ""
        Write-Host "  Запустите скрипт снова после установки недостающих компонентов." -ForegroundColor White
        Write-Host ""
    }
}

# ============================================================================
# ГЛАВНАЯ ФУНКЦИЯ
# ============================================================================

function Main {
    Write-Banner

    if ($CheckOnly) {
        Write-Host "  Режим проверки (без установки)" -ForegroundColor Yellow
        Write-Host ""
    }

    if (-not (Test-Admin)) {
        Write-Warning "Скрипт запущен без прав администратора"
        Write-Info "Некоторые компоненты (WSL) могут потребовать запуска от администратора"
        Write-Host ""
    }

    # Выполняем все шаги
    Step-CheckPython
    Step-CheckWSL

    # Проверяем, можно ли продолжать с WSL
    if ($script:Results["WSL"].Status -eq "OK") {
        Step-CheckUbuntu

        if ($script:Results["Ubuntu"].Status -eq "OK" -or $script:Results["Ubuntu"].Status -eq "INSTALLED") {
            Step-CheckNodeJS
            Step-CheckClaudeCLI
            Step-SetupWslVenv
        }
    } else {
        # Увеличиваем счётчик пропущенных шагов
        $script:CurrentStep += 5
    }

    Step-SetupWindowsVenv

    if ($script:Results["WSL"].Status -eq "OK") {
        Step-CheckGitHubCLI
    } else {
        $script:CurrentStep++
    }

    Write-Summary
}

# Запуск
Main
