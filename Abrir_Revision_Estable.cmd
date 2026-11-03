@echo off
cd /d "%~dp0"
"%~dp0.venv\Scripts\python.exe" -B "%~dp0scripts\start_stable_review.py"
if errorlevel 1 pause
