@echo off
chcp 65001 >nul
rem Buduje jeden plik OCR-PAKIET.exe dla stanowisk bez Pythona (folder dist\OCR-PAKIET).
cd /d "%~dp0"
call .venv\Scripts\activate.bat || (echo Najpierw uruchom instaluj.bat & pause & exit /b 1)
python -m pip install pyinstaller
pyinstaller --noconfirm --windowed --name OCR-PAKIET ^
  --collect-all winrt --hidden-import win32timezone ^
  --distpath dist start.py
copy /y pakiety_szablon.xlsx dist\OCR-PAKIET\ >nul
echo.
echo Gotowe: dist\OCR-PAKIET\OCR-PAKIET.exe  (skopiuj cały folder na stanowisko)
pause
