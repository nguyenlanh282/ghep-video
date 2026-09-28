@echo off
rem Mo app Ghep Video tren Windows. Chua cai dat thi tu cai roi mo app.
set PYTHONUTF8=1
set "PYW=%APPDATA%\GhepVideo\venv\Scripts\pythonw.exe"
if not exist "%PYW%" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0studio\setup-windows.ps1"
  exit /b
)
rem Thieu thu vien (cai do dang, bi diet virus xoa...): chay lai buoc cai dat, xong tu mo app.
"%APPDATA%\GhepVideo\venv\Scripts\python.exe" -c "import importlib.util as u,sys; sys.exit(any(u.find_spec(m) is None for m in ('numpy','PIL','webview','faster_whisper','cv2')))" 2>nul
if errorlevel 1 (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0studio\setup-windows.ps1"
  exit /b
)
start "" "%PYW%" "%~dp0studio\app\main.py"
