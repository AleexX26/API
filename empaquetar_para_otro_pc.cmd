@echo off
rem Crea dist\API-para-otro-pc.zip con todo lo necesario (sin los entornos de Python, que se recrean en el otro PC).
cd /d "%~dp0"
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -like '*app.collectors*' } | ForEach-Object { Write-Host 'ATENCION: hay una recogida en marcha. Ejecuta antes parar_recogida.cmd'; exit 1 }"
if errorlevel 1 ( pause & exit /b 1 )
if exist ".venv\Scripts\python.exe" ".venv\Scripts\python.exe" -c "import sqlite3; d=sqlite3.connect('data/catalog.sqlite3', timeout=60); d.execute('PRAGMA wal_checkpoint(TRUNCATE)'); d.close()"
if not exist "dist" mkdir "dist"
if exist "dist\API-para-otro-pc.zip" del "dist\API-para-otro-pc.zip"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$root = (Get-Location).Path; $tmp = Join-Path $env:TEMP 'API-para-otro-pc'; if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }; New-Item -ItemType Directory $tmp | Out-Null; $skip = '\\(\.venv|\.venv-browser|\.uv-cache|\.test-runs|\.pytest_cache|__pycache__|dist)(\\|$)'; Get-ChildItem $root -Recurse -File -Force | Where-Object { $_.FullName -notmatch $skip -and $_.Name -notlike '*.sqlite3-wal' -and $_.Name -notlike '*.sqlite3-shm' } | ForEach-Object { $rel = $_.FullName.Substring($root.Length + 1); $dest = Join-Path (Join-Path $tmp 'API') $rel; New-Item -ItemType Directory (Split-Path $dest) -Force | Out-Null; Copy-Item $_.FullName $dest }; Compress-Archive -Path (Join-Path $tmp 'API') -DestinationPath (Join-Path $root 'dist\API-para-otro-pc.zip') -CompressionLevel Optimal; Remove-Item $tmp -Recurse -Force"
echo.
echo Creado: dist\API-para-otro-pc.zip
echo Copialo al otro PC (USB, nube...), descomprimelo y sigue docs\MIGRACION.md
pause
