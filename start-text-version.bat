@echo off
REM The text-only version - useful if the app window won't open, because it shows errors.
cd /d "%~dp0"
title Wisp (text version)
py -V:3.13 text_mode.py
pause
