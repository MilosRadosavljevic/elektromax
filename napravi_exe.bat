@echo off
REM Pravi samostalan program kase: dist\ElektromaxKasa\ElektromaxKasa.exe
REM Ceo folder dist\ElektromaxKasa se kopira na racunar za kasom (Python tamo nije potreban).
cd /d "%~dp0"
.venv\Scripts\python -m pip install -r requirements-kasa.txt pyinstaller
.venv\Scripts\pyinstaller --noconfirm --clean --windowed --name ElektromaxKasa ^
  --paths . --paths kasa ^
  --hidden-import obracun --hidden-import fiskal --hidden-import dokumenti ^
  kasa\main.py
echo.
echo Gotovo: dist\ElektromaxKasa\ElektromaxKasa.exe
pause
