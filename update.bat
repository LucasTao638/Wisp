@echo off
REM Update Wisp safely: drag the new wisp.zip onto this file (or just double-click it).
cd /d "%~dp0"
title Updating Wisp
echo Closing Wisp if it's running...
taskkill /F /FI "WINDOWTITLE eq Wisp*" >nul 2>nul
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name like 'python%%.exe'\" | Where-Object { $_.CommandLine -like '*%~dp0*app.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>nul
py -V:3.13 "%~dp0updater.py" %1
echo.
echo Installing any new packages...
py -V:3.13 -m pip install -q -r "%~dp0requirements.txt"
echo.
echo Done! Starting Wisp...
call "%~dp0start.bat"
timeout /t 4 >nul
