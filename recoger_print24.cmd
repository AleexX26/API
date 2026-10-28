@echo off
rem Recoge las fichas de Print24 que faltan (las ya descargadas salen de data\cache y no se vuelven a pedir).
rem Pausa de 5 s entre peticiones, sin cookies. Ejecutalo en UN solo PC a la vez.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Falta el entorno. Ejecuta primero preparar_pc_nuevo.cmd
  pause
  exit /b 1
)
if not exist "data\registros" mkdir "data\registros"
echo Recogiendo Print24... (no cierres esta ventana)
".venv\Scripts\python.exe" -m app.collectors.products >> data\registros\print24.json 2>> data\registros\print24.log
echo Leyendo las caracteristicas de las fichas nuevas...
".venv\Scripts\python.exe" -m app.collectors.specs
echo.
echo Terminado. Mira el estado con estado_recogida.cmd
pause
