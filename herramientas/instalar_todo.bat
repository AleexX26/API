@echo off
setlocal
rem ============================================================
rem  Instala TODO lo necesario en un PC nuevo: Git, Python, el codigo
rem  del comparador (GitHub) y, si esta junto a este archivo, los datos.
rem  Copia SOLO este archivo (y API-datos.zip si lo tienes) al PC nuevo
rem  y haz doble clic. Hace falta Windows 10/11 con internet.
rem ============================================================
title Instalar comparador de imprentas
set "REPO=https://github.com/AleexX26/API.git"
set "DEST=%USERPROFILE%\Desktop\Proyectos\API"
set "AQUI=%~dp0"

echo.
echo === 1/5 Comprobando winget ===
where winget >nul 2>nul
if errorlevel 1 (
  echo No se encuentra winget. Abre la Microsoft Store, actualiza "Instalador de aplicacion" y vuelve a ejecutar este archivo.
  pause & exit /b 1
)

echo.
echo === 2/5 Git ===
where git >nul 2>nul
if errorlevel 1 (
  winget install --id Git.Git -e --silent --accept-package-agreements --accept-source-agreements
) else (
  echo Git ya esta instalado.
)
set "PATH=%PATH%;C:\Program Files\Git\cmd"

echo.
echo === 3/5 Python 3.12 ===
python --version >nul 2>nul
if errorlevel 1 (
  winget install --id Python.Python.3.12 -e --silent --accept-package-agreements --accept-source-agreements
) else (
  echo Python ya esta instalado.
)
rem el alias de la Microsoft Store (python.exe vacio) puede ir antes en el PATH: ponemos la carpeta real la primera
set "PATH=%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts;%PATH%"

echo.
echo === 4/5 Codigo del comparador ===
where git >nul 2>nul
if errorlevel 1 (
  echo Git no se ha podido instalar. Cierra esta ventana, abre otra y ejecuta este archivo de nuevo.
  pause & exit /b 1
)
if exist "%DEST%\.git" (
  echo Ya existe %DEST%: se actualiza con git pull.
  git -C "%DEST%" pull
) else (
  if not exist "%USERPROFILE%\Desktop\Proyectos" mkdir "%USERPROFILE%\Desktop\Proyectos"
  echo Descargando de GitHub. Si es privado, se abrira el navegador para iniciar sesion.
  git clone %REPO% "%DEST%"
)
if not exist "%DEST%\app" (
  echo No se ha descargado el codigo. Revisa la sesion de GitHub y vuelve a ejecutar este archivo.
  pause & exit /b 1
)

echo.
echo === 5/5 Datos y entorno ===
set "ZIP="
if exist "%AQUI%API-datos.zip" set "ZIP=%AQUI%API-datos.zip"
if not defined ZIP if exist "%USERPROFILE%\Downloads\API-datos.zip" set "ZIP=%USERPROFILE%\Downloads\API-datos.zip"
if not defined ZIP goto sinzip
if not exist "%DEST%\data\catalog.sqlite3" goto ponerdatos
echo AVISO: este PC ya tiene una base de datos. Si sigues, se SUSTITUYE por la del ZIP.
choice /c SN /n /m "Sustituir los datos por los del ZIP? (S/N) "
if errorlevel 2 goto omitirdatos
:ponerdatos
echo Descomprimiendo %ZIP% ...
powershell -NoProfile -Command "Expand-Archive -LiteralPath '%ZIP%' -DestinationPath '%DEST%\data' -Force"
goto entorno
:sinzip
echo No he encontrado API-datos.zip (junto a este archivo ni en Descargas). Se instala sin datos.
goto entorno
:omitirdatos
echo Se mantienen los datos que ya habia en este PC.
:entorno
if exist "%DEST%\herramientas\preparar_pc_nuevo.cmd" (
  call "%DEST%\herramientas\preparar_pc_nuevo.cmd"
)

echo.
echo ============================================================
echo  LISTO. Carpeta: %DEST%
echo  - Abrir el comparador:         Abrir comparador.cmd
echo  - Compartirlo en la oficina:   Abrir comparador para la oficina.cmd
echo  - Recoger datos (UN solo PC a la vez): herramientas\recogida\reanudar_recogida.cmd y recoger_print24.cmd
echo ============================================================
pause
endlocal
