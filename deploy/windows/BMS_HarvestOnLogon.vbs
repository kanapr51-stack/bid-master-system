' BMS_HarvestOnLogon.vbs — รัน harvest_and_push ทันทีตอน login (catch-up on reconnect)
' ติดตั้ง: copy ไป %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\
' ทำให้: เปิดเครื่อง/login → harvest token สด → push VPS → trigger discovery_catchup
'         (ถ้าพลาด scheduled slot 07/13/19 ตอนเครื่องปิด → รัน discovery ทันที)
' เหตุผลต้องใช้ vbs (ไม่แก้ task trigger): BMS_TokenHarvest task แก้ trigger ต้อง admin
Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Bid-Master-System"
WshShell.Run "C:\Users\Ace\AppData\Local\Python\pythoncore-3.14-64\python.exe scripts\harvest_and_push.py", 0, False
