' BMS — รัน harvest_task.bat แบบซ่อนหน้าต่าง (ไม่มี console flash)
' ใช้โดย Task Scheduler ทุก 25 นาที
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run """C:\Bid-Master-System\scripts\harvest_task.bat""", 0, False
