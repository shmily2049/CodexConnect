@echo off
setlocal
cd /d "%~dp0"
if exist "CodeXConnect-0.10.7.exe" (
  start "" "%~dp0CodeXConnect-0.10.7.exe"
  exit /b
)
where py >nul 2>nul
if not errorlevel 1 (
  py -3 app.py
) else (
  python app.py
)
if errorlevel 1 (
  echo Install Python 3.11 or newer with Tcl/Tk from https://www.python.org/downloads/
  pause
)
