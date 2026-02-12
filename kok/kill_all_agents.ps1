# Tayfa — убить всех агентов (удалить в Claude API и остановить сервер)
# Использование: .\kill_all_agents.ps1   или   powershell -ExecutionPolicy Bypass -File kill_all_agents.ps1

$base = "http://localhost:8000"
try {
    $r = Invoke-RestMethod -Uri "$base/api/kill-all-agents?stop_server=true" -Method Post
    Write-Host "Удалено агентов: $($r.deleted -join ', ')"
    if ($r.errors.Count -gt 0) {
        Write-Host "Ошибки:" -ForegroundColor Yellow
        $r.errors | ForEach-Object { Write-Host "  $($_.name): $($_.error)" }
    }
    Write-Host "Сервер: $($r.stop_server.status)" -ForegroundColor Green
} catch {
    Write-Host "Ошибка: $_" -ForegroundColor Red
    Write-Host "Убедитесь, что оркестратор запущен (run.bat или run.ps1)." -ForegroundColor Yellow
    exit 1
}
