@echo off
chcp 65001 >nul
echo.
echo   Building Tayfa.exe...
echo.

cd /d "%~dp0"

REM Activate venv
call venv\Scripts\activate.bat 2>nul
if %errorlevel% neq 0 (
    echo   [!] venv not found. Run tayfa.bat first to create it.
    pause
    exit /b 1
)

REM Install PyInstaller if not present
pip show pyinstaller >nul 2>&1
if %errorlevel% neq 0 (
    echo   Installing PyInstaller...
    pip install pyinstaller
    if %errorlevel% neq 0 (
        echo   [!] Failed to install PyInstaller.
        pause
        exit /b 1
    )
)

echo   Running PyInstaller...
pyinstaller --onefile --noconsole --icon=static/tayfa-icon.ico --name=Tayfa --distpath=. --clean -y tayfa_launcher.py

if %errorlevel% neq 0 (
    echo   [!] PyInstaller failed.
    pause
    exit /b 1
)

REM Clean up build artifacts
echo   Cleaning up...
rmdir /s /q build 2>nul
del /q Tayfa.spec 2>nul

echo.
echo   ========================================
echo   Done! Tayfa.exe created.
echo   ========================================
echo.

pause
