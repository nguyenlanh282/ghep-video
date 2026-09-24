@echo off
rem Mo app Ghep Video tren Windows.
set PYTHONUTF8=1
set "PYW=%APPDATA%\GhepVideo\venv\Scripts\pythonw.exe"
if not exist "%PYW%" (
  echo Chua cai dat. Hay chay "Cai dat (Windows).bat" truoc.
  pause
  exit /b 1
)
start "" "%PYW%" "%~dp0studio\app\main.py"
