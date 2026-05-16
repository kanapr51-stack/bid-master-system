@echo off
REM ============================================================
REM  Pipeline NOTIFY — รัน 06:00 ทุกวัน
REM  classify (rebuild dates) → LINE notify (ส่งตรงเวลา)
REM  ไม่ใช้ Chrome เพราะ data เก็บไว้แล้วตอน 02:00
REM ============================================================

cd /d C:\Bid-Master-System
if not exist logs mkdir logs

SET PYTHON=C:\Users\Ace\AppData\Local\Python\bin\python.exe
SET LOGFILE=C:\Bid-Master-System\logs\pipeline_notify_%date:~10,4%%date:~4,2%%date:~7,2%.txt

echo ============================================================ >> %LOGFILE%
echo [%TIME%] NOTIFY phase START >> %LOGFILE%
echo ============================================================ >> %LOGFILE%

%PYTHON% scripts\ask_discord.py --notify "🌅 **06:00 — Notify phase START** classify rebuild + LINE notify"

REM --- Step 1: CLASSIFY (rebuild — picks up date changes) ---
echo [%TIME%] Classify rebuild (refresh days_remaining + move passed deadlines) >> %LOGFILE%
%PYTHON% scripts\Sebastian_Pipeline.py --step classify >> %LOGFILE% 2>&1
if errorlevel 1 (
    echo [%TIME%] Classify failed — continue to notify ด้วย sheet เดิม >> %LOGFILE%
)

REM --- Step 2: NOTIFY (LINE + Discord summary) ---
echo [%TIME%] LINE Notify >> %LOGFILE%
%PYTHON% scripts\Sebastian_Pipeline.py --step notify >> %LOGFILE% 2>&1
SET NOTIFY_EXIT=%ERRORLEVEL%

if %NOTIFY_EXIT% EQU 0 (
    echo [%TIME%] NOTIFY phase DONE >> %LOGFILE%
    %PYTHON% scripts\ask_discord.py --notify "✅ **LINE ส่งแล้ว 06:00** — Pipeline เสร็จสิ้น 🎉"
) else (
    echo [%TIME%] NOTIFY phase FAILED (exit %NOTIFY_EXIT%) >> %LOGFILE%
    %PYTHON% scripts\ask_discord.py --notify "❌ **NOTIFY phase ผิดพลาด** (exit %NOTIFY_EXIT%) — ตรวจ log: pipeline_notify_%date:~10,4%%date:~4,2%%date:~7,2%.txt"
)

echo ============================================================ >> %LOGFILE%
