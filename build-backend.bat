@echo off
echo Building Python backend executable with PyInstaller...
python -m pip install pyinstaller
python -m pip install -r requirements.txt
pyinstaller --noconfirm --clean --strip --name gat-backend --distpath dist-backend --paths src ^
  --exclude-module tkinter --exclude-module PyQt5 --exclude-module PyQt6 ^
  --exclude-module PySide2 --exclude-module PySide6 --exclude-module wx ^
  backend_launcher.py
echo Backend executable: dist-backend\gat-backend\gat-backend.exe
