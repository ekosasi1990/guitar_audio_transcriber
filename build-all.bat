@echo off
echo Building Guitar Audio Transcriber (backend + frontend)...
call build-backend.bat
call setup.bat
npm run dist
echo Done. Installer is in the dist/ folder.
pause
