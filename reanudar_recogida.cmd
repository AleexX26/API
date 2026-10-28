@echo off
rem Reanuda la recogida de Onlineprinters y Printai en segundo plano (TusKamisetas queda fuera: son ropa y ~21 h;
rem para incluirlo, quita el rem de la linea de recogida-tuskamisetas).
rem Lo ya descargado esta en data\cache y no se vuelve a pedir; solo se piden las paginas que faltan.
rem IMPORTANTE: ejecutalo en UN solo PC a la vez (el otro debe estar parado: parar_recogida.cmd).
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Falta el entorno. Ejecuta primero preparar_pc_nuevo.cmd
  pause
  exit /b 1
)
if not exist "data\registros" mkdir "data\registros"
echo Lanzando las recogidas en segundo plano...
rem start "recogida-tuskamisetas" /min cmd /c ".venv\Scripts\python.exe -m app.collectors.tuskamisetas --sitemap >> data\registros\tuskamisetas.json 2>> data\registros\tuskamisetas.log"
start "recogida-onlineprinters" /min cmd /c ".venv\Scripts\python.exe -m app.collectors.onlineprinters >> data\registros\onlineprinters.json 2>> data\registros\onlineprinters.log"
start "recogida-printai" /min cmd /c ".venv\Scripts\python.exe -m app.collectors.printai --sitemap >> data\registros\printai.json 2>> data\registros\printai.log"
echo.
echo Hecho. Se ven como ventanas minimizadas en la barra de tareas; NO las cierres.
echo   Ver como va:  estado_recogida.cmd
echo   Pararlo todo: parar_recogida.cmd
echo   Registros:    data\registros\
echo.
echo Consejo: en Configuracion de energia pon "Suspender: nunca" mientras dure (Onlineprinters tarda ~3 horas).
pause
