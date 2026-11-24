@echo off
REM Removes Wisp's shortcuts and stops it starting with Windows. Your files stay in this folder until you delete it.
cd /d "%~dp0"
echo Closing Wisp...
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name like 'python%%.exe'\" | Where-Object { $_.CommandLine -like '*%~dp0*app.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>nul
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Wisp.lnk" >nul 2>nul
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Wisp.lnk" >nul 2>nul
reg delete "HKCU\Software\Wisp" /f >nul 2>nul
for /f "usebackq delims=" %%d in (`powershell -NoProfile -Command "[Environment]::GetFolderPath('Desktop')"`) do del "%%d\Wisp.lnk" >nul 2>nul
echo.
echo Wisp's shortcuts are removed. To finish, delete this folder:
echo   %~dp0
echo (It contains your settings and memory - keep a copy if you might come back.)
pause
