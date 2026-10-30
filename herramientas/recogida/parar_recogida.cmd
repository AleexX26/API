@echo off
rem Para todas las recogidas. Lo ya guardado se conserva y se puede reanudar con reanudar_recogida.cmd
cd /d "%~dp0\..\.."
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -like '*app.collectors*' -or $_.CommandLine -like '*web_server.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
echo Recogidas paradas.
rem Deja la base de datos en un solo archivo (necesario antes de copiarla a otro PC)
if exist ".venv\Scripts\python.exe" ".venv\Scripts\python.exe" -c "import sqlite3; d=sqlite3.connect('data/catalog.sqlite3', timeout=60); print('checkpoint', d.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()); d.close()"
pause
