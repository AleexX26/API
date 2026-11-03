@echo off
rem Recoge los precios de las tarjetas de visita de NUESTRA web (laimprentadeinternet.com): todas las combinaciones del configurador.
rem Abre un navegador, cambia las opciones de la propia pagina y apunta el precio de cada una (pausa de 5 s). Dura unos 8 minutos.
rem Los precios ya leidos se guardan 30 dias: si lo repites antes, no pide nada. Necesita Playwright (requirements-test.txt).
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
if not exist "data\registros" mkdir "data\registros"
echo Leyendo los precios de nuestra web... (no cierres esta ventana)
".venv\Scripts\python.exe" -m app.collectors.laimprentadeinternet 2>> data\registros\laimprentadeinternet.log
echo.
echo Terminado. Abre el comparador para verlos.
pause
