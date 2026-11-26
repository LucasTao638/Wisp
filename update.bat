@echo off
REM Update Wisp safely: drag the new wisp.zip onto this file (or just double-click it).
cd /d "%~dp0"
REM Use Wisp's own Python (in .venv) if it has one, otherwise the system Python 3.13
set PY=py -V:3.13
if exist "%~dp0.venv\Scripts\python.exe" set PY="%~dp0.venv\Scripts\python.exe"
title Updating Wisp
echo Closing Wisp if it's running...
taskkill /F /FI "WINDOWTITLE eq Wisp*" >nul 2>nul
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name like 'python%%.exe'\" | Where-Object { $_.CommandLine -like '*%~dp0*app.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>nul
%PY% "%~dp0updater.py" %1
echo.
echo Installing any new packages...
if not exist "%~dp0.venv\Scripts\python.exe" goto :systempip
"%USERPROFILE%\.local\bin\uv.exe" pip install -q --python "%~dp0.venv\Scripts\python.exe" -r "%~dp0requirements.txt"
goto :packagesdone
:systempip
py -V:3.13 -m pip install -q -r "%~dp0requirements.txt"
:packagesdone
echo.
echo Done! Starting Wisp...
call "%~dp0start.bat"
timeout /t 4 >nul
