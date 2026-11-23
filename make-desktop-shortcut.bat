@echo off
REM Puts a "Wisp" shortcut on your desktop that opens the app.
cd /d "%~dp0"
powershell -NoProfile -Command "$s = (New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop') + '\Wisp.lnk'); $s.TargetPath = '%~dp0start.bat'; $s.WorkingDirectory = '%~dp0'; $s.WindowStyle = 7; $s.Description = 'Wisp AI assistant'; $s.Save()"
echo Done! There's now a Wisp shortcut on your desktop.
pause
