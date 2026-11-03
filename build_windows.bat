@echo off
setlocal
cd /d "%~dp0"
if not exist .venv-build\Scripts\python.exe (
  py -3.12 -m venv .venv-build
  if errorlevel 1 exit /b 1
)
.venv-build\Scripts\python.exe -m pip install -r requirements-build.txt
if errorlevel 1 exit /b 1
.venv-build\Scripts\python.exe -m PyInstaller --noconfirm --clean Auricle.spec
if errorlevel 1 exit /b 1
.venv-build\Scripts\python.exe packaging\smoke_native.py
if errorlevel 1 exit /b 1
.venv-build\Scripts\python.exe packaging\package_release.py windows-x64
if errorlevel 1 exit /b 1
echo Build complete: out\
endlocal
