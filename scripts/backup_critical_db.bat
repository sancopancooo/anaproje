@echo off
REM Haftalık kritik DB yedeği — çift tıkla veya Task Scheduler'a bağla
cd /d "%~dp0.."
if exist "venv\Scripts\python.exe" (
  "venv\Scripts\python.exe" scripts\backup_critical_db.py %*
) else (
  py -3 scripts\backup_critical_db.py %*
)
echo.
pause
