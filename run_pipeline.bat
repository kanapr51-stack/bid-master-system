@echo off
REM ============================================================
REM  Sebastian Pipeline Runner — รันอัตโนมัติทุกวัน 06:00 น.
REM  Log: C:\Bid-Master-System\logs\pipeline_YYYYMMDD.txt
REM ============================================================

cd /d C:\Bid-Master-System
if not exist logs mkdir logs

SET PYTHON=C:\Users\Ace\AppData\Local\Python\bin\python.exe
SET CHROME="C:\Program Files\Google\Chrome\Application\chrome.exe"
SET LOGFILE=C:\Bid-Master-System\logs\pipeline_%date:~10,4%%date:~4,2%%date:~7,2%.txt

echo ============================================================ >> %LOGFILE%
echo [%TIME%] Sebastian Pipeline เริ่มต้น >> %LOGFILE%
echo ============================================================ >> %LOGFILE%

%PYTHON% scripts\ask_discord.py --notify "🚀 **Sebastian** Pipeline เริ่มต้น %TIME:~0,5% น. — กำลังดึงข้อมูล eGP..."

REM --- Kill Chrome Debug เก่าก่อน (PowerShell — wmic ถูกลบใน Win11 25H2) ---
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | Where-Object { $_.CommandLine -like '*ChromeDebug*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" > nul 2>&1
timeout /t 5 /nobreak > nul

REM --- ลบ lock files เก่า (Singleton* คือ lock จริงของ Chrome, ไม่ใช่ lockfile) ---
if exist "C:\Temp\ChromeDebug\SingletonLock"   del /f "C:\Temp\ChromeDebug\SingletonLock"   > nul 2>&1
if exist "C:\Temp\ChromeDebug\SingletonCookie" del /f "C:\Temp\ChromeDebug\SingletonCookie" > nul 2>&1
if exist "C:\Temp\ChromeDebug\SingletonSocket" del /f "C:\Temp\ChromeDebug\SingletonSocket" > nul 2>&1
if exist "C:\Temp\ChromeDebug\lockfile"        del /f "C:\Temp\ChromeDebug\lockfile"        > nul 2>&1

REM --- เปิด Chrome Debug (profile แยก ไม่กระทบ Chrome หลัก) ---
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
    echo [%TIME%] ERROR: Chrome ไม่ผูก port 9222 ภายใน 60 วินาที — ข้าม Step 1 และ Step 3 >> %LOGFILE%
    %PYTHON% scripts\ask_discord.py --notify "❌ **Chrome Debug ไม่ขึ้น** — ข้าม Scraper และ Winner Checker (port 9222 ไม่ตอบ)"
)

REM --- Step 1: Scrape (ต้องการ Chrome) ---
if "%CHROME_OK%"=="1" (
    echo [%TIME%] Step 1: Scraper >> %LOGFILE%
    %PYTHON% scripts\Sebastian_Pipeline.py --step scrape >> %LOGFILE% 2>&1
    if errorlevel 1 (
        %PYTHON% scripts\ask_discord.py --notify "❌ **Step 1** Scraper ผิดพลาด — ดู log: pipeline_%date:~10,4%%date:~4,2%%date:~7,2%.txt"
    ) else (
        %PYTHON% scripts\ask_discord.py --notify "✅ **Step 1** Scraper เสร็จ"
    )
) else (
    echo [%TIME%] Step 1: Scraper — SKIP (Chrome ไม่พร้อม) >> %LOGFILE%
)

REM --- Step 2: Classify (ไม่ต้องการ Chrome) ---
echo [%TIME%] Step 2: Classify >> %LOGFILE%
%PYTHON% scripts\Sebastian_Pipeline.py --step classify >> %LOGFILE% 2>&1
if %ERRORLEVEL% NEQ 0 (
    %PYTHON% scripts\ask_discord.py --notify "❌ **Step 2** Classifier ผิดพลาด — ดู log: pipeline_%date:~10,4%%date:~4,2%%date:~7,2%.txt"
) else (
    %PYTHON% scripts\ask_discord.py --notify "✅ **Step 2** Classifier เสร็จ"
)

REM --- Step 3: Winner Checker (ต้องการ Chrome) ---
if "%CHROME_OK%"=="1" (
    echo [%TIME%] Step 3: Winner Checker >> %LOGFILE%
    %PYTHON% scripts\Sebastian_Winner_Checker.py >> %LOGFILE% 2>&1
    if errorlevel 1 (
        %PYTHON% scripts\ask_discord.py --notify "❌ **Step 3** Winner Checker ผิดพลาด — ดู log: pipeline_%date:~10,4%%date:~4,2%%date:~7,2%.txt"
    ) else (
        %PYTHON% scripts\ask_discord.py --notify "✅ **Step 3** Winner Checker เสร็จ"
    )
) else (
    echo [%TIME%] Step 3: Winner Checker — SKIP (Chrome ไม่พร้อม) >> %LOGFILE%
)

REM --- ปิด Chrome Debug (PowerShell — wmic ถูกลบใน Win11 25H2) ---
echo [%TIME%] ปิด Chrome Debug... >> %LOGFILE%
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | Where-Object { $_.CommandLine -like '*ChromeDebug*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" > nul 2>&1

REM --- Step 4: LINE Notify ---
echo [%TIME%] Step 4: LINE Notify >> %LOGFILE%
%PYTHON% scripts\Sebastian_LINE_Notify.py >> %LOGFILE% 2>&1
if %ERRORLEVEL% NEQ 0 (
    %PYTHON% scripts\ask_discord.py --notify "❌ **Step 4** LINE Notify ผิดพลาด — ดู log: pipeline_%date:~10,4%%date:~4,2%%date:~7,2%.txt"
) else (
    %PYTHON% scripts\ask_discord.py --notify "✅ **Step 4** LINE ส่งแล้ว — Pipeline เสร็จสิ้น 🎉"
)

echo [%TIME%] Pipeline เสร็จสิ้น >> %LOGFILE%
echo ============================================================ >> %LOGFILE%
