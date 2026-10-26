@echo off
chcp 65001 >nul
title Rooter Local OTP Login Helper
cls
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
echo ===================================================
echo     Rooter Local Login Helper (Indian IP)
echo ===================================================
echo.
C:\Users\aakas\.python_embed\python.exe login_rooter.py
pause
