@echo off
cd /d "%~dp0.."
if defined CV_PYTHON (set PY=%CV_PYTHON%) else if exist "%~dp0..\..\_venv\Scripts\python.exe" (set PY=%~dp0..\..\_venv\Scripts\python.exe) else (set PY=python)
"%PY%" scripts\reset_for_shoot.py
pause
