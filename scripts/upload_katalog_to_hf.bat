@echo off
cd /d "%~dp0.."
echo katalog.db Hugging Face'e yukleniyor...
if exist "venv\Scripts\python.exe" (
  "venv\Scripts\python.exe" scripts\upload_katalog_to_hf.py %*
) else (
  py -3 scripts\upload_katalog_to_hf.py %*
)
pause
