@echo off
title PlayStation Gift Card Telegram Bot
echo ============================================================
echo Starting PlayStation Gift Card Telegram Buyer Bot...
echo ============================================================

REM Use portable python if present, or system python
if exist "C:\Users\aakas\.python_embed\python.exe" (
    "C:\Users\aakas\.python_embed\python.exe" main.py
) else (
    python main.py
)

pause
