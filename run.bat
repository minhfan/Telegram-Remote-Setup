@echo off
REM ── Telegram Remote Setup — chạy trên Windows (cần Python 3 đã cài) ──
REM Double-click file này. Lần đầu nó tự cài customtkinter rồi mở app.
cd /d "%~dp0"
echo [*] Kiem tra / cai customtkinter...
python -m pip install --quiet --disable-pip-version-check customtkinter
echo [*] Mo Telegram Remote Setup...
python app.py
if errorlevel 1 (
  echo.
  echo [!] Co loi. Thuong la chua cai Python:
  echo     - Tai Python 3 o https://python.org/downloads
  echo     - Khi cai, NHO tich "Add Python to PATH"
  echo     - Roi double-click lai run.bat
  pause
)
