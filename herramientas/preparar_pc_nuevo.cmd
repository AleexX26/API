@echo off
rem Prepara este PC: crea el entorno de Python e instala lo necesario. Ejecutar UNA vez tras copiar la carpeta.
cd /d "%~dp0.."
echo.
echo === Comprobando Python ===
python --version >nul 2>&1
if errorlevel 1 (
  echo No encuentro Python. Instala Python 3.12 desde https://www.python.org/downloads/
  echo ^(marca la casilla "Add python.exe to PATH"^) o con:  winget install Python.Python.3.12
  echo Despues vuelve a ejecutar este archivo.
  pause
  exit /b 1
)
python --version
python -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)"
if errorlevel 1 (
  echo Hace falta Python 3.11 o superior.
  pause
  exit /b 1
)
echo.
echo === Creando entorno .venv ===
if exist ".venv" rmdir /s /q ".venv"
python -m venv .venv
if errorlevel 1 ( echo Fallo al crear el entorno. & pause & exit /b 1 )
echo.
echo === Instalando dependencias ===
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt -r requirements-web.txt
if errorlevel 1 ( echo Fallo al instalar. Revisa la conexion a Internet. & pause & exit /b 1 )
echo.
echo === Pasando los tests ===
".venv\Scripts\python.exe" -m pytest -q --basetemp ".test-runs\nuevo-pc"
echo.
echo === Estado de lo recogido ===
".venv\Scripts\python.exe" -m app.collectors.status
echo.
echo Listo. Siguiente paso: abrir el comparador (Abrir comparador.cmd) o recoger datos (herramientas\recogida\reanudar_recogida.cmd)
pause
