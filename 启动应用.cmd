@echo off
setlocal
cd /d "%~dp0"
set "APP=%~dp0release\CodexConnect-0.10.13\CodexConnect-0.10.13.exe"
if not exist "%APP%" set "APP=%~dp0work\build-artifacts\0.10.13\windows-dist\CodexConnect.exe"
if not exist "%APP%" set "APP=%~dp0tools\windows\dist\CodexConnect.exe"
if not exist "%APP%" (
  echo Application not found in release or tools\windows\dist.
  echo Restore the Windows EXE or build it before launching.
  pause
  exit /b 1
)
if /i "%~1"=="--smoke-ui" (
  start "" /wait "%APP%" --smoke-ui
  exit /b
)
start "" "%APP%"
