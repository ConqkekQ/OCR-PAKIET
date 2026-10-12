@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\pythonw.exe (
  echo Najpierw uruchom instaluj.bat
  pause
  exit /b 1
)
start "" .venv\Scripts\pythonw.exe -m ocr_pakiet
