@echo off
REM run_rss_scraper.bat - RSS scraper wrapper for Task Scheduler

setlocal
cd /d "%~dp0\.."

if not exist "logs\rss" mkdir "logs\rss"

for /f "usebackq" %%t in (`powershell -NoProfile -Command "Get-Date -Format 'yyyyMMdd_HHmmss'"`) do set "TS=%%t"

python scripts\Sebastian_RSS_Scraper.py --queue >> "logs\rss\rss_%TS%.log" 2>&1
exit /b %ERRORLEVEL%
