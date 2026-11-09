@echo off
REM Pokrece Elektromax demo na http://127.0.0.1:5000
cd /d "%~dp0"
if not exist .venv (
  echo Pravim virtuelno okruzenje i instaliram Flask...
  python -m venv .venv
  .venv\Scripts\python -m pip install -r requirements.txt
)
start "" http://127.0.0.1:5000
.venv\Scripts\python app.py
