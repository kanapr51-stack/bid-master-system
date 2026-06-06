Set-Location "C:\Bid-Master-System"
$LogDir = "C:\Bid-Master-System\logs\cgd"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Force -Path $LogDir | Out-Null }
$LogFile = Join-Path $LogDir "winner_refresh_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"
# refresh winner_history.db (residential IP — CGD 403 จาก VPS). auto-ingest FY2569 เมื่อ DGA publish
python scripts\cgd_winner_refresh.py 2>&1 | Tee-Object -FilePath $LogFile
# [P1 deploy-debt 2026-06-01] หยุด push data ลง git (กัน conflict กับ VPS) — state เขียน local เท่านั้น
Get-ChildItem (Join-Path $LogDir "winner_refresh_*.log") | Sort-Object CreationTime | Select-Object -SkipLast 7 | Remove-Item -Force
