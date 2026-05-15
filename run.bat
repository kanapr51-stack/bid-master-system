@echo off
echo ========================================
echo   Bid Master System - เริ่มต้นระบบ
echo ========================================
echo.

echo [1/3] ปิด Chrome เดิม ...
taskkill /f /im chrome.exe >nul 2>&1
timeout /t 2 >nul

echo [2/3] เปิด Chrome พร้อม debug port ...
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" ^
  --remote-debugging-port=9222 ^
  --user-data-dir="C:\Bid-Master-System\chrome_debug_profile" ^
  --no-first-run
timeout /t 5 >nul

echo [3/3] รัน Python script ...
echo.
py "C:\Bid-Master-System\scripts\Sebastian Python Pull Data.py"

echo.
echo ========================================
echo   เสร็จสิ้น
echo ========================================
pause
