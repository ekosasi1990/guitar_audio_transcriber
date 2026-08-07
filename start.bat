@echo off
echo Starting Guitar Audio Transcriber...

start "GAT Backend" python -m uvicorn src.backend.api:app --reload
timeout /t 2 >nul
start "GAT Frontend" npm start

echo Backend: http://127.0.0.1:8000
echo Frontend window should appear shortly.
