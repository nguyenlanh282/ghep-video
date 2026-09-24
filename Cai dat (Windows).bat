@echo off
rem Cai dat Ghep Video tren Windows (co the chay lai). Xong se tu mo app.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0studio\setup-windows.ps1"
if errorlevel 1 pause
