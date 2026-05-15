@echo off
echo ปิด Chrome เดิม ...
taskkill /f /im chrome.exe >nul 2>&1
timeout /t 2 >nul

echo เปิด Chrome ด้วย profile จริง ...
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\Users\Ace\AppData\Local\Google\Chrome\User Data" --profile-directory=Default --no-first-run

echo.
echo ✅ Chrome เปิดแล้ว!
echo กรุณาไปที่: https://www.gprocurement.go.th/new_index.html
echo จากนั้นกลับมา VS Code แล้วรัน Python script
pause
