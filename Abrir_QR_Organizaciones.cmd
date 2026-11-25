@echo off
cd /d "%~dp0"
"%~dp0.venv\Scripts\python.exe" -B "%~dp0scripts\open_organization_qr.py"
if errorlevel 1 pause
