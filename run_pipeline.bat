@echo off
REM ============================================================
REM  Sebastian Pipeline Runner — รันอัตโนมัติทุกวัน 06:00 น.
REM  Pipeline 8 steps: scrape → classify → refresh → download → analyze → cost → rank → notify
REM  Log: C:\Bid-Master-System\logs\pipeline_YYYYMMDD.txt
REM ============================================================

cd /d C:\Bid-Master-System
if not exist logs mkdir logs

SET PYTHON=C:\Users\Ace\AppData\Local\Python\bin\python.exe
SET CHROME="C:\Program Files\Google\Chrome\Application\chrome.exe"
SET LOGFILE=C:\Bid-Master-System\logs\pipeline_%date:~10,4%%date:~4,2%%date:~7,2%.txt

echo ============================================================ >> %LOGFILE%
echo [%TIME%] Sebastian Pipeline เริ่มต้น (8-step) >> %LOGFILE%
echo ============================================================ >> %LOGFILE%

REM --- Discord: pipeline starting ---
%PYTHON% scripts\ask_discord.py --notify "🚀 **Sebastian Pipeline** เริ่มต้น %TIME:~0,5% น. — 8 steps + Chrome auto-launch"

REM ============================================================
REM Chrome Debug — kill old + launch new + wait for port 9222
REM ============================================================

REM --- Kill Chrome Debug เก่า ---
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | Where-Object { $_.CommandLine -like '*ChromeDebug*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" > nul 2>&1
timeout /t 5 /nobreak > nul

REM --- ลบ lock files เก่า ---
if exist "C:\Temp\ChromeDebug\SingletonLock"   del /f "C:\Temp\ChromeDebug\SingletonLock"   > nul 2>&1
if exist "C:\Temp\ChromeDebug\SingletonCookie" del /f "C:\Temp\ChromeDebug\SingletonCookie" > nul 2>&1
if exist "C:\Temp\ChromeDebug\SingletonSocket" del /f "C:\Temp\ChromeDebug\SingletonSocket" > nul 2>&1
if exist "C:\Temp\ChromeDebug\lockfile"        del /f "C:\Temp\ChromeDebug\lockfile"        > nul 2>&1

REM --- เปิด Chrome Debug ---
echo [%TIME%] เปิด Chrome Debug... >> %LOGFILE%
start "" %CHROME% --remote-debugging-port=9222 --no-first-run --no-restore-last-session --disable-session-crashed-bubble --user-data-dir=C:\Temp\ChromeDebug --window-position=0,0 --window-size=800,600

REM --- รอ Chrome ผูก port 9222 (health-check, fail fast ภายใน ~60 วินาที) ---
SET CHROME_OK=0
powershell -NoProfile -Command "$ok=$false; for($i=0;$i -lt 30;$i++){ try { Invoke-WebRequest -Uri 'http://127.0.0.1:9222/json/version' -UseBasicParsing -TimeoutSec 2 | Out-Null; $ok=$true; break } catch { Start-Sleep -Seconds 2 } }; if(-not $ok){ exit 1 }"
if %ERRORLEVEL% EQU 0 (
    timeout /t 5 /nobreak > nul
    SET CHROME_OK=1
    echo [%TIME%] Chrome Debug พร้อมใช้งาน (port 9222) >> %LOGFILE%
) else (
    echo [%TIME%] ERROR: Chrome ไม่ผูก port 9222 ภายใน 60 วินาที — ข้าม scrape/refresh/download >> %LOGFILE%
    %PYTHON% scripts\ask_discord.py --notify "❌ **Chrome Debug ไม่ขึ้น** — Pipeline จะข้าม Chrome-dependent steps (scrape/refresh/download)"
)

REM ============================================================
REM Pipeline 8 steps — Sebastian_Pipeline.py orchestrates
REM (Pipeline.py ภายในมี Discord notify per step + auto-skip ถ้า Chrome ไม่พร้อม)
REM ============================================================

echo [%TIME%] รัน Sebastian_Pipeline.py --step all >> %LOGFILE%
%PYTHON% scripts\Sebastian_Pipeline.py --step all >> %LOGFILE% 2>&1
SET PIPELINE_EXIT=%ERRORLEVEL%

REM ============================================================
REM Cleanup — kill Chrome Debug
REM ============================================================

echo [%TIME%] ปิด Chrome Debug... >> %LOGFILE%
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | Where-Object { $_.CommandLine -like '*ChromeDebug*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" > nul 2>&1

REM ============================================================
REM Final status
REM ============================================================

if %PIPELINE_EXIT% EQU 0 (
    echo [%TIME%] Pipeline เสร็จสิ้น (success) >> %LOGFILE%
    %PYTHON% scripts\ask_discord.py --notify "✅ **Pipeline เสร็จสิ้น** — ดูสรุปใน LINE group + log: pipeline_%date:~10,4%%date:~4,2%%date:~7,2%.txt"
) else (
    echo [%TIME%] Pipeline ผิดพลาด (exit %PIPELINE_EXIT%) >> %LOGFILE%
    %PYTHON% scripts\ask_discord.py --notify "❌ **Pipeline ผิดพลาด** (exit %PIPELINE_EXIT%) — ดู log: pipeline_%date:~10,4%%date:~4,2%%date:~7,2%.txt"
)

echo ============================================================ >> %LOGFILE%
