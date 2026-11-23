@echo off
REM Installs everything Wisp needs, using the files in this folder.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" -Local
if errorlevel 1 (
  echo.
  echo Something went wrong - see the messages above.
)
pause
