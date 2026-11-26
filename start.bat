@echo off
REM Starts the Wisp app window (no Command Prompt left open).
cd /d "%~dp0"
REM Use Wisp's own Python (in .venv) if it has one, otherwise the system Python 3.13
set PY=py -V:3.13
if exist "%~dp0.venv\Scripts\python.exe" set PY="%~dp0.venv\Scripts\python.exe"
%PY% -c "import tkinter" >nul 2>nul
if errorlevel 1 (
  echo The app window needs tkinter, which is missing - opening the text version instead.
  call "%~dp0start-text-version.bat"
  exit /b
)
if not exist "%~dp0.venv\Scripts\pythonw.exe" goto :systempython
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0app.py"
exit /b
:systempython
for /f "delims=" %%i in ('%PY% -c "import sys, os; print(os.path.join(os.path.dirname(sys.executable), 'pythonw.exe'))"') do set "PYW=%%i"
if exist "%PYW%" (
  start "" "%PYW%" "%~dp0app.py"
) else (
  %PY% "%~dp0app.py"
)
