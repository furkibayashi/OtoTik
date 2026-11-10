@echo off
REM OtoTik.exe derleme betigi (Windows). Gereksinim: Python 3.9+
py -m pip install -r requirements.txt pyinstaller
py -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name OtoTik ^
  --icon assets\icon.ico ^
  --add-data "assets;assets" ^
  --collect-data customtkinter ^
  OtoTik.pyw
echo.
echo Hazir: dist\OtoTik.exe
pause
