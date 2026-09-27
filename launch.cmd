@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" server.py
  exit /b
)
where py >nul 2>nul
if not errorlevel 1 (
  py server.py
  exit /b
)
where python >nul 2>nul
if not errorlevel 1 (
  python server.py
  exit /b
)
if exist "%LOCALAPPDATA%\Python\pythoncore-3.11-64\python.exe" (
  "%LOCALAPPDATA%\Python\pythoncore-3.11-64\python.exe" server.py
  exit /b
)
echo Install Python 3.11 or newer, then run py server.py.
exit /b 1
