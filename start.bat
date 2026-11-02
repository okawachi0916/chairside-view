@echo off
cd /d "%~dp0"
if "%CV_PORT%"=="" set CV_PORT=8840
if defined CV_PYTHON (set PY=%CV_PYTHON%) else if exist "%~dp0..\_venv\Scripts\python.exe" (set PY=%~dp0..\_venv\Scripts\python.exe) else (set PY=python)
"%PY%" -m uvicorn app.main:app --host 0.0.0.0 --port %CV_PORT% --reload
