Set-Location "C:\Bid-Master-System"
$LogFile = "C:\Bid-Master-System\logs\cgd\cgd_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"
python scripts\cgd_discovery.py --provinces "นครพนม" --max-calls 600 2>&1 | Tee-Object -FilePath $LogFile
# [P1 deploy-debt 2026-06-01] หยุด push data ลง git (กัน conflict กับ VPS) — state เขียน local เท่านั้น
Get-ChildItem "C:\Bid-Master-System\logs\cgd\cgd_*.log" | Sort-Object CreationTime | Select-Object -SkipLast 7 | Remove-Item -Force
