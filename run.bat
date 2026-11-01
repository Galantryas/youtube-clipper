@echo off
title YouTube Clipper Pro
echo ===================================================
echo             YouTube Clipper Pro Starter
echo ===================================================
echo.
py --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python was not found. Please install Python 3.10+ from python.org.
    pause
    exit /b 1
)

echo [+] Checking and starting YouTube Clipper Pro...
py run.py
pause
