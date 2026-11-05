@echo off
rem Todas las herramientas en un solo menu. Doble clic, o con argumento: Herramientas.cmd recoger|importar|estado|parar|preparar|empaquetar
cd /d "%~dp0.."
set "PY=.venv\Scripts\python.exe"
if not "%~1"=="" ( call :%~1 %2 & exit /b )

:menu
cls
echo ==============================================
echo   HERRAMIENTAS DEL COMPARADOR
echo ==============================================
echo   1  Recoger datos (todo en uno)
echo   2  Importar el Excel de tarifas de nuestra web
echo   3  Ver como va la recogida
echo   4  Parar la recogida
echo   5  Preparar este PC (primera vez)
echo   6  Empaquetar para llevar a otro PC
echo   0  Salir
echo.
set "OP="
set /p OP=Elige una opcion:
if "%OP%"=="1" call :recoger
if "%OP%"=="2" call :importar
if "%OP%"=="3" call :estado
if "%OP%"=="4" call :parar
if "%OP%"=="5" call :preparar
if "%OP%"=="6" call :empaquetar
if "%OP%"=="0" exit /b
echo.
pause
goto menu

:entorno
if not exist "%PY%" (
  echo Falta el entorno. Elige la opcion 5 ^(Preparar este PC^).
  exit /b 1
)
exit /b 0

:recoger
rem Print24 (fichas, caracteristicas y cantidades hasta 1000), nuestra web y, si quieres, Onlineprinters y Printai en segundo plano.
rem Lo ya descargado esta en data\cache y no se vuelve a pedir. Ejecutalo en UN solo PC a la vez.
call :entorno || exit /b 1
if not exist "data\registros" mkdir "data\registros"
echo.
choice /c HR /n /m "Pausa entre pasos: [H] humana, al azar entre 30 s y 1 min (recomendada)  [R] rapida, 5-8 s (solo pruebas): "
if errorlevel 2 (
  set "PAUSA_MIN=5"
  set "PAUSA_MAX=8"
) else (
  set "PAUSA_MIN=30"
  set "PAUSA_MAX=60"
)
echo Pausa elegida: entre %PAUSA_MIN% y %PAUSA_MAX% segundos, distinta cada vez. Con pausa humana la recogida tarda muchas horas: dejala en el otro PC.
echo === Print24: fichas nuevas ===
"%PY%" -m app.collectors.products >> data\registros\print24.json 2>> data\registros\print24.log
"%PY%" -m app.collectors.specs
"%PY%" -m app.collectors.laimprentadeinternet --sitemap
echo.
choice /c TS /n /m "Cantidades de Print24: [T] todas las fichas, muchas horas  [S] solo tarjetas de visita: "
set "ALL=%errorlevel%"
echo.
choice /c TCN /n /m "Truyol: [T] tarjetas y flyers, varias horas  [C] todo su catalogo, muchas horas  [N] no recoger Truyol: "
set "TRU=%errorlevel%"
echo.
choice /c SN /n /m "Print24: [S] precios exactos de las tarjetas por gramaje, caras y acabado, muchas horas  [N] no: "
set "P24OPT=%errorlevel%"
"%PY%" -c "import playwright" 2>nul
if errorlevel 1 (
  echo.
  echo Falta Playwright: me salto las cantidades de Print24 y nuestra web.
  echo Instalalo con: %PY% -m pip install -r requirements-test.txt  y luego  %PY% -m playwright install chromium
) else (
  echo.
  echo === Print24: mas cantidades, hasta 1000 ===
  if "%ALL%"=="1" ( "%PY%" -m app.collectors.print24_quantities --todas ) else ( "%PY%" -m app.collectors.print24_quantities )
  echo.
  if "%P24OPT%"=="1" (
    echo === Print24: tarjetas por gramaje, caras y acabado ===
    "%PY%" -m app.collectors.print24_options
  )
  echo.
  echo === Nuestra web: tarjetas, flyers, folletos, triptico y diptico ^(varias horas^) ===
  "%PY%" -m app.collectors.laimprentadeinternet 2>> data\registros\laimprentadeinternet.log
  echo.
  echo === Truyol ===
  if "%TRU%"=="1" ( "%PY%" -m app.collectors.truyol --grupo todos 2>> data\registros\truyol.log )
  if "%TRU%"=="2" ( "%PY%" -m app.collectors.truyol --grupo catalogo 2>> data\registros\truyol.log )
)
echo.
set "BG="
set /p BG=Lanzar tambien Onlineprinters y Printai en segundo plano [unas 3 horas]? [s/N]:
if /i "%BG%"=="s" (
  start "recogida-onlineprinters" /min cmd /c "%PY% -m app.collectors.onlineprinters >> data\registros\onlineprinters.json 2>> data\registros\onlineprinters.log"
  start "recogida-printai" /min cmd /c "%PY% -m app.collectors.printai --sitemap >> data\registros\printai.json 2>> data\registros\printai.log"
  echo Lanzadas como ventanas minimizadas: NO las cierres. Mira como van con la opcion 3.
)
echo.
echo Terminado. Reinicia el comparador para ver los datos nuevos.
exit /b 0

:importar
rem Carga los precios de venta de nuestra web desde el Excel de tarifas (todas las hojas). Sustituye los anteriores.
call :entorno || exit /b 1
set "EXCEL=%~1"
if "%EXCEL%"=="" set /p EXCEL=Ruta del Excel de tarifas [puedes arrastrar el archivo aqui]:
set "EXCEL=%EXCEL:"=%"
"%PY%" -m app.collectors.tarifa_propia "%EXCEL%"
echo.
echo Hecho. Reinicia el comparador para ver los precios.
exit /b 0

:estado
call :entorno || exit /b 1
echo === Procesos de recogida activos ===
powershell -NoProfile -Command "$r = Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -like '*app.collectors*' }; if ($r) { $r | ForEach-Object { '  ' + $_.CommandLine.Substring($_.CommandLine.IndexOf('-m')) } } else { '  (ninguno: esta parado)' }"
echo.
echo === Lo recogido ===
"%PY%" -m app.collectors.status
echo.
echo === Ultima linea de cada registro ===
for %%f in (data\registros\*.log) do (
  echo %%f:
  powershell -NoProfile -Command "Get-Content '%%f' -Tail 1"
)
exit /b 0

:parar
rem Para todas las recogidas. Lo ya guardado se conserva y se reanuda con la opcion 1.
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -like '*app.collectors*' -or $_.CommandLine -like '*web_server.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
echo Recogidas paradas.
rem Deja la base de datos en un solo archivo (necesario antes de copiarla a otro PC)
if exist "%PY%" "%PY%" -c "import sqlite3; d=sqlite3.connect('data/catalog.sqlite3', timeout=60); print('checkpoint', d.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()); d.close()"
exit /b 0

:preparar
rem Crea el entorno de Python e instala lo necesario. UNA vez tras copiar la carpeta.
echo === Comprobando Python ===
python --version >nul 2>&1
if errorlevel 1 (
  echo No encuentro Python. Instala Python 3.12 desde https://www.python.org/downloads/
  echo ^(marca "Add python.exe to PATH"^) o con:  winget install Python.Python.3.12
  exit /b 1
)
python --version
python -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)"
if errorlevel 1 (
  echo Hace falta Python 3.11 o superior.
  exit /b 1
)
echo.
echo === Creando entorno .venv ===
if exist ".venv" rmdir /s /q ".venv"
python -m venv .venv
if errorlevel 1 ( echo Fallo al crear el entorno. & exit /b 1 )
echo.
echo === Instalando dependencias ===
"%PY%" -m pip install --upgrade pip
"%PY%" -m pip install -r requirements.txt -r requirements-web.txt
if errorlevel 1 ( echo Fallo al instalar. Revisa la conexion a Internet. & exit /b 1 )
echo.
echo === Pasando los tests ===
"%PY%" -m pytest -q --basetemp ".test-runs\nuevo-pc"
echo.
echo === Estado de lo recogido ===
"%PY%" -m app.collectors.status
echo.
echo Listo. Siguiente paso: Abrir comparador.cmd o la opcion 1 de este menu.
exit /b 0

:empaquetar
rem Crea dist\API-para-otro-pc.zip con todo lo necesario (sin los entornos de Python, que se recrean en el otro PC).
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -like '*app.collectors*' } | ForEach-Object { Write-Host 'ATENCION: hay una recogida en marcha. Usa antes la opcion 4 (Parar)'; exit 1 }"
if errorlevel 1 exit /b 1
if exist "%PY%" "%PY%" -c "import sqlite3; d=sqlite3.connect('data/catalog.sqlite3', timeout=60); d.execute('PRAGMA wal_checkpoint(TRUNCATE)'); d.close()"
if not exist "dist" mkdir "dist"
if exist "dist\API-para-otro-pc.zip" del "dist\API-para-otro-pc.zip"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$root = (Get-Location).Path; $tmp = Join-Path $env:TEMP 'API-para-otro-pc'; if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }; New-Item -ItemType Directory $tmp | Out-Null; $skip = '\\(\.venv|\.venv-browser|\.uv-cache|\.test-runs|\.pytest_cache|__pycache__|dist)(\\|$)'; Get-ChildItem $root -Recurse -File -Force | Where-Object { $_.FullName -notmatch $skip -and $_.Name -notlike '*.sqlite3-wal' -and $_.Name -notlike '*.sqlite3-shm' } | ForEach-Object { $rel = $_.FullName.Substring($root.Length + 1); $dest = Join-Path (Join-Path $tmp 'API') $rel; New-Item -ItemType Directory (Split-Path $dest) -Force | Out-Null; Copy-Item $_.FullName $dest }; Compress-Archive -Path (Join-Path $tmp 'API') -DestinationPath (Join-Path $root 'dist\API-para-otro-pc.zip') -CompressionLevel Optimal; Remove-Item $tmp -Recurse -Force"
echo.
echo Creado: dist\API-para-otro-pc.zip
echo Copialo al otro PC, descomprimelo y sigue docs\MIGRACION.md
exit /b 0
