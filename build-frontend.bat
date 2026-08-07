@echo off
echo Building Guitar Audio Transcriber Windows installer...
npm install
npm run dist
echo Done. Installer is in the dist/ folder.
pause
