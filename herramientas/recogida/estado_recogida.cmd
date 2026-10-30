@echo off
cd /d "%~dp0\..\.."
echo === Procesos de recogida activos ===
powershell -NoProfile -Command "$r = Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -like '*app.collectors*' }; if ($r) { $r | ForEach-Object { '  ' + $_.CommandLine.Substring($_.CommandLine.IndexOf('-m')) } } else { '  (ninguno: esta parado)' }"
echo.
echo === Lo recogido ===
".venv\Scripts\python.exe" -m app.collectors.status
echo.
echo === Ultima linea de cada registro ===
for %%f in (data\registros\*.log) do (
  echo %%f:
  powershell -NoProfile -Command "Get-Content '%%f' -Tail 1"
)
pause
