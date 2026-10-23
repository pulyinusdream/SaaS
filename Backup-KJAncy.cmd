@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Start the app with Start-KJAncy.cmd once to create its Python environment.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" backup.py create
pause
