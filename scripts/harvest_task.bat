@echo off
REM BMS token harvest + push to VPS — รันโดย Task Scheduler ทุก 25 นาที
cd /d C:\Bid-Master-System
if not exist logs mkdir logs
"C:\Users\Ace\AppData\Local\Python\pythoncore-3.14-64\python.exe" scripts\harvest_and_push.py >> logs\harvest.log 2>&1
