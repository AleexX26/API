@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Falta el entorno Python. Consulta README.md.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" web_server.py --open
pause
