@echo off
REM Removes Wisp: shortcuts, start-at-login, its entry in Settings > Apps, and (if you want) its folder.
REM Claude Code and uv stay installed - other apps may use them.
cd /d "%~dp0"
title Uninstall Wisp
echo.
echo === Uninstalling Wisp ===
echo Closing Wisp...
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name like 'python%%.exe'\" | Where-Object { $_.CommandLine -like '*%~dp0*app.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>nul
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Wisp.lnk" >nul 2>nul
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Wisp.lnk" >nul 2>nul
for /f "usebackq delims=" %%d in (`powershell -NoProfile -Command "[Environment]::GetFolderPath('Desktop')"`) do del "%%d\Wisp.lnk" >nul 2>nul
reg delete "HKCU\Software\Wisp" /f >nul 2>nul
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\Wisp" /f >nul 2>nul
echo Shortcuts removed.
echo.
echo Wisp's folder is:  %~dp0
echo It also holds your settings and Wisp's memory.
choice /c YN /n /m "Delete the folder too? [Y = delete everything / N = keep it] "
if errorlevel 2 goto :keep
echo Deleting Wisp's folder...
set "WISPDIR=%~dp0"
cd /d "%TEMP%"
REM a separate window deletes the folder once this one has closed (a folder can't be deleted while it's in use)
start "" /min cmd /c "timeout /t 4 /nobreak >nul & rmdir /s /q "%WISPDIR%""
echo Wisp has been removed.
timeout /t 2 >nul
exit
:keep
echo Wisp has been removed. Its folder (with your settings and memory) is kept - delete it any time.
pause
