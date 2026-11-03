@echo off
rem Carga en el comparador los precios de venta de NUESTRA web desde el Excel de tarifas (hoja "TARJETAS DE VISITA").
rem Arrastra el archivo .xlsx encima de este icono, o ejecutalo y escribe la ruta. Sustituye los precios anteriores de nuestra web en las tarjetas.
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo Falta el entorno. Ejecuta primero herramientas\preparar_pc_nuevo.cmd
  pause
  exit /b 1
)
set "EXCEL=%~1"
if "%EXCEL%"=="" set /p EXCEL=Ruta del Excel de tarifas: 
".venv\Scripts\python.exe" -m app.collectors.tarifa_propia "%EXCEL%"
echo.
echo Hecho. Reinicia el comparador para ver los precios.
pause
