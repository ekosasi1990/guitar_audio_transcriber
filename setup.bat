@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  python -m venv .venv
  if errorlevel 1 goto failed
)

echo Installing Python dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements-dev.txt
if errorlevel 1 goto failed

echo Installing desktop dependencies...
call npm ci
if errorlevel 1 goto failed

echo Setup complete. Open start.bat to launch the app.
pause
exit /b 0

:failed
echo Setup failed. Check the message above and confirm Python and Node.js are installed.
pause
exit /b 1
