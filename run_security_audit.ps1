# Принудительная установка кодировки UTF-8 в выводе консоли
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "  1. ЗАПУСК SAST (Bandit - Анализ безопасности кода)" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
.\.venv\Scripts\bandit.exe -r apps packages -c .bandit.yaml

Write-Host "`n=========================================" -ForegroundColor Yellow
Write-Host "  2. ЗАПУСК SCA (Pip-Audit - Проверка CVE зависимостей)" -ForegroundColor Yellow
Write-Host "=========================================" -ForegroundColor Yellow
.\.venv\Scripts\pip-audit.exe --desc

Write-Host "`n=========================================" -ForegroundColor Magenta
Write-Host "  3. ЗАПУСК SEMGREP (Паттерны OWASP Top-10 & CWE)" -ForegroundColor Magenta
Write-Host "=========================================" -ForegroundColor Magenta
.\.venv\Scripts\semgrep.exe scan --config "p/security-audit" --config "p/secrets" apps packages