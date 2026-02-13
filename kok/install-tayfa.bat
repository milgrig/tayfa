@echo off
chcp 65001 >nul 2>&1
title Tayfa Installer

echo.
echo   ████████╗ █████╗ ██╗   ██╗███████╗ █████╗
echo   ╚══██╔══╝██╔══██╗╚██╗ ██╔╝██╔════╝██╔══██╗
echo      ██║   ███████║ ╚████╔╝ █████╗  ███████║
echo      ██║   ██╔══██║  ╚██╔╝  ██╔══╝  ██╔══██║
echo      ██║   ██║  ██║   ██║   ██║     ██║  ██║
echo      ╚═╝   ╚═╝  ╚═╝   ╚═╝   ╚═╝     ╚═╝  ╚═╝
echo.
echo          Запуск установщика...
echo.

powershell -ExecutionPolicy Bypass -File "%~dp0install-tayfa.ps1" %*

echo.
echo Нажмите любую клавишу для выхода...
pause >nul
