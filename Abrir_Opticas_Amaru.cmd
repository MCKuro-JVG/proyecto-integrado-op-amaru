@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Abrir_Opticas_Amaru.ps1"
if errorlevel 1 pause
