@echo off
chcp 65001 >nul
title Tayfa Orchestrator
color 0B

echo.
echo   ========================================
echo.
echo    TTTTT   AAA   Y   Y  FFFFF   AAA
echo      T    A   A   Y Y   F      A   A
echo      T    AAAAA    Y    FFFF   AAAAA
echo      T    A   A    Y    F      A   A
echo      T    A   A    Y    F      A   A
echo.
echo    Orchestrator
echo.
echo   ========================================
echo.

REM === Capture optional project path argument ===
set "PROJECT_ARG="
if not "%~1"=="" (
    set "PROJECT_ARG=--project "%~1""
)

cd /d "%~dp0"

REM === Create shortcut on first run ===
if not exist "Tayfa.lnk" (
    if exist "create_shortcut.vbs" (
        if exist "static\tayfa-icon.ico" (
            echo   [*] Creating desktop shortcut...
            cscript //nologo create_shortcut.vbs >nul 2>&1
            if exist "Tayfa.lnk" (
                echo       Tayfa.lnk created!
            ) else (
                echo       Note: Shortcut creation skipped.
            )
            echo.
        )
    )
)

echo   [1/4] Python...
where python >nul 2>&1
if %errorlevel% neq 0 (
    where py >nul 2>&1
    if %errorlevel% neq 0 (
        echo.
        echo   [!] Python not found!
        echo       Install Python 3: https://python.org
        echo.
        pause
        exit /b 1
    )
    set PY_CMD=py
) else (
    set PY_CMD=python
)

for /f "tokens=*" %%v in ('%PY_CMD% --version 2^>^&1') do echo         %%v
echo.

echo   [2/4] Virtual environment...
if not exist "venv\Scripts\activate.bat" (
    echo         Creating venv...
    %PY_CMD% -m venv venv
    if %errorlevel% neq 0 (
        echo   [!] Failed to create venv.
        pause
        exit /b 1
    )
    echo         Done.
) else (
    echo         venv OK.
)
echo.

call venv\Scripts\activate.bat

echo   [3/4] Dependencies...
pip install -q -r requirements.txt >nul 2>&1
if %errorlevel% neq 0 (
    echo   [!] Failed to install dependencies.
    pause
    exit /b 1
)
echo         Done.
echo.

echo   [4/4] Starting Tayfa Orchestrator...
echo.
echo   =========================================
echo.
echo     Browser will open automatically.
echo     Port is selected dynamically (8008, 8009, ...).
echo     WSL + Claude API will start on launch.
if not "%PROJECT_ARG%"=="" (
echo.
echo     Project: %~1
)
echo.
echo     Press Ctrl+C to stop.
echo.
echo   =========================================
echo.

python app.py %PROJECT_ARG%

if %errorlevel% neq 0 (
    echo.
    echo   [!] Tayfa crashed with error code %errorlevel%
    echo.
    pause
    exit /b %errorlevel%
)

echo.
echo   Tayfa stopped.
echo.
