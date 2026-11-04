@echo off
rem 撮影の前に、試しに入れたものを消して見本の状態へ戻す（今のデータベースは控えに残す）
cd /d "%~dp0.."
"C:\hackathon\work\_venv\Scripts\python.exe" scriptseset_for_shoot.py
pause
