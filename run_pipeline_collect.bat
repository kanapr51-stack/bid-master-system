@echo off
REM ============================================================
REM  Pipeline COLLECT — รัน 02:00 ทุกวัน
REM  scrape → classify → refresh (เก็บข้อมูลพร้อมส่ง 06:00)
REM ============================================================

setlocal enabledelayedexpansion
cd /d C:\Bid-Master-System
if not exist logs mkdir logs

SET PYTHON=C:\Users\Ace\AppData\Local\Python\bin\python.exe
SET CHROME="C:\Program Files\Google\Chrome\Application\chrome.exe"
SET LOGFILE=C:\Bid-Master-System\logs\pipeline_collect_%date:~10,4%%date:~4,2%%date:~7,2%.txt

echo ============================================================ >> %LOGFILE%
echo [%TIME%] COLLECT phase START >> %LOGFILE%
echo ============================================================ >> %LOGFILE%

%PYTHON% scripts\ask_discord.py --notify "🌙 **02:00 — Collect phase START** ดึงข้อมูล eGP (~50 นาที)"

REM --- Kill old Chrome + launch new ---
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | Where-Object { $_.CommandLine -like '*ChromeDebug*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" > nul 2>&1
timeout /t 5 /nobreak > nul
if exist "C:\Temp\ChromeDebug\SingletonLock"   del /f "C:\Temp\ChromeDebug\SingletonLock"   > nul 2>&1
if exist "C:\Temp\ChromeDebug\SingletonCookie" del /f "C:\Temp\ChromeDebug\SingletonCookie" > nul 2>&1
if exist "C:\Temp\ChromeDebug\SingletonSocket" del /f "C:\Temp\ChromeDebug\SingletonSocket" > nul 2>&1
if exist "C:\Temp\ChromeDebug\lockfile"        del /f "C:\Temp\ChromeDebug\lockfile"        > nul 2>&1

echo [%TIME%] เปิด Chrome Debug... >> %LOGFILE%
REM Stealth flags (2026-05-17): disable AutomationControlled + realistic window size
start "" %CHROME% --remote-debugging-port=9222 ^
  --disable-blink-features=AutomationControlled ^
  --disable-features=IsolateOrigins,site-per-process,AutomationControlled ^
  --no-first-run --no-default-browser-check ^
  --no-restore-last-session --disable-session-crashed-bubble ^
  --user-data-dir=C:\Temp\ChromeDebug ^
  --window-position=0,0 --window-size=1280,800

REM --- Wait for Chrome port 9222 ---
SET CHROME_OK=0
powershell -NoProfile -Command "$ok=$false; for($i=0;$i -lt 30;$i++){ try { Invoke-WebRequest -Uri 'http://127.0.0.1:9222/json/version' -UseBasicParsing -TimeoutSec 2 | Out-Null; $ok=$true; break } catch { Start-Sleep -Seconds 2 } }; if(-not $ok){ exit 1 }"
if !ERRORLEVEL! EQU 0 (
    timeout /t 5 /nobreak > nul
    SET CHROME_OK=1
    echo [%TIME%] Chrome Debug พร้อม ^(port 9222^) >> %LOGFILE%
) else (
    echo [%TIME%] ERROR: Chrome ไม่ผูก port 9222 — ข้าม scrape/refresh >> %LOGFILE%
    %PYTHON% scripts\ask_discord.py --notify "❌ Chrome ไม่ขึ้น (collect) — ข้าม scrape/refresh"
)

REM --- Step 1: SCRAPE (Chrome required) ---
if "!CHROME_OK!"=="1" (
    echo [%TIME%] Step 1: SCRAPE >> %LOGFILE%
    %PYTHON% scripts\Sebastian_Pipeline.py --step scrape >> %LOGFILE% 2>&1
)

REM --- Step 2: CLASSIFY ---
echo [%TIME%] Step 2: CLASSIFY >> %LOGFILE%
%PYTHON% scripts\Sebastian_Pipeline.py --step classify >> %LOGFILE% 2>&1

REM --- Step 3: REFRESH (Chrome required) ---
if "!CHROME_OK!"=="1" (
    echo [%TIME%] Step 3: REFRESH (active + tor + pending) >> %LOGFILE%
    %PYTHON% scripts\refresh_active_jobs.py --expand >> %LOGFILE% 2>&1
)

REM --- Step 4: PATCH_DEADLINES (Chrome required) ---
REM ดึง deadline จาก PDF ของ active jobs ที่ deadline ว่าง — มี retry 2 ครั้ง
if "!CHROME_OK!"=="1" (
    echo [%TIME%] Step 4: PATCH_DEADLINES (active jobs missing deadline) >> %LOGFILE%
    %PYTHON% scripts\patch_deadlines.py >> %LOGFILE% 2>&1
)

REM --- Step 5: CLASSIFY (final — apply new deadlines) ---
echo [%TIME%] Step 5: CLASSIFY final (apply patched deadlines) >> %LOGFILE%
%PYTHON% scripts\Sebastian_Pipeline.py --step classify >> %LOGFILE% 2>&1

REM --- Cleanup: Kill Chrome ---
echo [%TIME%] ปิด Chrome Debug... >> %LOGFILE%
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | Where-Object { $_.CommandLine -like '*ChromeDebug*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" > nul 2>&1

echo [%TIME%] COLLECT phase DONE — รอ NOTIFY phase 06:00 >> %LOGFILE%
%PYTHON% scripts\ask_discord.py --notify "✅ **Collect phase DONE** — รอ 06:00 ส่ง LINE notify"
echo ============================================================ >> %LOGFILE%
endlocal
