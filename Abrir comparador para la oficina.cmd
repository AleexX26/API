@echo off
rem Abre el comparador y lo comparte con los demas PC de la misma red (solo lectura para ellos).
rem Muestra el enlace que deben escribir. Windows puede preguntar por el Firewall: permitelo en "Redes privadas".
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Falta el entorno Python. Consulta README.md.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" web_server.py --open --lan
pause
