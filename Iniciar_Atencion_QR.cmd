@echo off
cd /d "%~dp0"
"%~dp0.venv\Scripts\python.exe" -B "%~dp0scripts\start_attention_review.py"
if errorlevel 1 pause
