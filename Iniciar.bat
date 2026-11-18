@echo off
cd /d "%~dp0"
where py >nul 2>nul && (py -3 avatar_studio.py %*) || (python avatar_studio.py %*)
pause
