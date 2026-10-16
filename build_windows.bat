@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Virtual environment not found. Run setup_windows.bat first.
  exit /b 1
)
call .venv\Scripts\activate.bat
python -m pip install -r requirements-windows.txt
if errorlevel 1 exit /b 1

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

python -m PyInstaller --noconfirm --clean Auricle.spec
if errorlevel 1 exit /b 1

echo.
echo Build complete: dist\Auricle\Auricle.exe
endlocal
