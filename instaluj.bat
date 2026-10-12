@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Instalacja OCR-PAKIET ===
where py >nul 2>nul && (set PY=py -3) || (set PY=python)
%PY% --version || (echo Brak Pythona. Zainstaluj Python 3.10+ z python.org i zaznacz "Add to PATH". & pause & exit /b 1)
if not exist .venv %PY% -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
echo.
echo Gotowe. Uruchamiaj programem uruchom.bat
pause
