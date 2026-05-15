@echo off
chcp 65001 > nul
title Sebastian Discord Bot

echo ====================================
echo  Sebastian Discord Bot
echo ====================================
echo.

cd /d "%~dp0"

:: ตรวจสอบ Python
python --version > nul 2>&1
if errorlevel 1 (
    echo [ERROR] ไม่พบ Python
    pause
    exit /b 1
)

:: รัน Bot (วนซ้ำอัตโนมัติถ้า crash)
:loop
echo [%TIME%] เริ่ม Sebastian Discord Bot...
python scripts\Sebastian_Discord_Bot.py
echo [%TIME%] Bot หยุดทำงาน (exit %ERRORLEVEL%) รอ 10 วินาทีก่อน restart...
timeout /t 10 /nobreak > nul
goto loop
