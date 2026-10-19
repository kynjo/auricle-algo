@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Virtual environment not found. Run setup_windows.bat first.
  exit /b 1
)
.venv\Scripts\python.exe -m pip install -r requirements-build.txt
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean Auricle.spec
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe packaging\package_release.py windows-x64
if errorlevel 1 exit /b 1
echo Build complete: dist\Auricle\Auricle.exe and the release ZIP in out\
endlocal
