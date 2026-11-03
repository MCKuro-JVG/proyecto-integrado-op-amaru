@echo off
cd /d "%~dp0"
"%~dp0.venv\Scripts\python.exe" -B "%~dp0scripts\attention_runtime.py" start
if errorlevel 1 pause
