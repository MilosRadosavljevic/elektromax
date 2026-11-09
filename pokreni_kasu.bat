@echo off
REM Pokrece desktop kasu iz izvornog koda (za razvoj/probu).
REM Server (pokreni.bat) mora da radi; adresa servera se unosi na ekranu za prijavu.
cd /d "%~dp0"
if not exist .venv (
  echo Prvo pokrenite pokreni.bat da se napravi okruzenje.
  pause
  exit /b 1
)
.venv\Scripts\python -m pip show PySide6-Essentials >nul 2>&1 || .venv\Scripts\python -m pip install -r requirements-kasa.txt
start "" .venv\Scripts\pythonw kasa\main.py
