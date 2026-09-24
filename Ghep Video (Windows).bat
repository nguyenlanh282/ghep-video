@echo off
rem Mo app Ghep Video tren Windows. Chua cai dat thi tu cai roi mo app.
set PYTHONUTF8=1
set "PYW=%APPDATA%\GhepVideo\venv\Scripts\pythonw.exe"
if not exist "%PYW%" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0studio\setup-windows.ps1"
  exit /b
)
start "" "%PYW%" "%~dp0studio\app\main.py"
