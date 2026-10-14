@echo off
setlocal
cd /d "%~dp0"
title Guitar Audio Transcriber
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" "tools\launch_app.py" %*
) else (
    python "tools\launch_app.py" %*
)
if errorlevel 1 (
    echo.
    echo Startup failed. See the message above.
    pause
    exit /b 1
)
exit /b 0
