@echo off
rem Recoge en Print24 mas cantidades (hasta 1000) de las tarjetas de visita basicas: abre un navegador, elige las cantidades en la lista
rem de la propia pagina como lo haria una persona y apunta los precios. Pausa de 5 s, sin cuentas. Dura menos de un minuto.
rem Necesita Playwright (requirements-test.txt). Ejecutalo en UN solo PC a la vez.
cd /d "%~dp0\..\.."
if not exist ".venv\Scripts\python.exe" (
  echo Falta el entorno. Ejecuta primero herramientas\preparar_pc_nuevo.cmd
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -c "import playwright" 2>nul
if errorlevel 1 (
  echo Falta Playwright. Instalalo con: .venv\Scripts\python.exe -m pip install -r requirements-test.txt
  echo y despues: .venv\Scripts\python.exe -m playwright install chromium
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m app.collectors.print24_quantities %*
echo.
echo Terminado. Reinicia el comparador para ver las cantidades nuevas.
pause
