@echo off
REM Lists the free neural voices (English ones) and lets you test one.
cd /d "%~dp0"
echo Some good ones to try:
echo   en-GB-RyanNeural      British male (the default)
echo   en-GB-ThomasNeural    British male, deeper
echo   en-AU-WilliamNeural   Australian male
echo   en-US-GuyNeural       American male
echo   en-US-AriaNeural      American female
echo   en-GB-SoniaNeural     British female
echo.
echo Full list of English voices:
py -V:3.13 -m edge_tts --list-voices | findstr /b /c:"Name" /c:"en-"
echo.
set /p VOICE=Type a voice name to hear it (or press Enter to skip): 
if "%VOICE%"=="" goto :eof
py -V:3.13 -c "import json,voice,threading; c=json.load(open('config.json')); c['voice_engine']='edge'; c['edge_voice']='%VOICE%'; d=threading.Event(); voice.Speaker(c).speak('Good evening. All systems are online and ready.', on_done=d.set); d.wait(30)"
echo.
echo To use it, open config.json and set  "edge_voice": "%VOICE%"
pause
