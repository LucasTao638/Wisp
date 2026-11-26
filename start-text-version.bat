@echo off
REM The text-only version - useful if the app window won't open, because it shows errors.
cd /d "%~dp0"
REM Use Wisp's own Python (in .venv) if it has one, otherwise the system Python 3.13
set PY=py -V:3.13
if exist "%~dp0.venv\Scripts\python.exe" set PY="%~dp0.venv\Scripts\python.exe"
title Wisp (text version)
%PY% text_mode.py
pause
