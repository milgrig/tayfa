@echo off
chcp 65001 >nul
title Tayfa — убить всех агентов

cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "try { $r = Invoke-RestMethod -Uri 'http://localhost:8000/api/kill-all-agents?stop_server=true' -Method Post; Write-Host 'Удалено агентов:' $r.deleted; Write-Host 'Сервер:' $r.stop_server.status } catch { Write-Host 'Ошибка. Запущен ли оркестратор (run.bat)?' -ForegroundColor Red; exit 1 }"

pause
