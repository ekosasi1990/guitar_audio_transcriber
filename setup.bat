@echo off
echo Installing Python dependencies...
python -m pip install -r requirements.txt

echo Installing Node dependencies...
npm install

echo Done. Run start.bat to launch the app.
pause
