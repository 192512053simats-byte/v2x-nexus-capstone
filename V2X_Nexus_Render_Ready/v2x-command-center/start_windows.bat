@echo off
cd /d "%~dp0"
title V2X Nexus - Local Research Dashboard
where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    start "" "http://127.0.0.1:5000"
    py -3 server.py
) else (
    start "" "http://127.0.0.1:5000"
    python server.py
)
echo.
echo If you saw a Python not found error, install Python 3.10+ from python.org
pause
