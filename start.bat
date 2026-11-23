@echo off
REM Starts the Wisp app window (no Command Prompt left open).
cd /d "%~dp0"
py -V:3.13 -c "import tkinter" >nul 2>nul
if errorlevel 1 (
  echo The app window needs tkinter, which is missing - opening the text version instead.
  call "%~dp0start-text-version.bat"
  exit /b
)
for /f "delims=" %%i in ('py -V:3.13 -c "import sys, os; print(os.path.join(os.path.dirname(sys.executable), 'pythonw.exe'))"') do set "PYW=%%i"
if exist "%PYW%" (
  start "" "%PYW%" "%~dp0app.py"
) else (
  py -V:3.13 "%~dp0app.py"
)
