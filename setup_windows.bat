@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
  echo Python Launcher ^(py^) was not found.
  echo Install Python 3.12 x64 from python.org and enable the Python Launcher.
  exit /b 1
)

py -3.12 -m venv .venv
if errorlevel 1 exit /b 1
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements-windows.txt

echo.
echo Auricle Windows environment is ready.
endlocal
