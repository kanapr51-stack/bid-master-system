Set-Location "C:\Bid-Master-System"
$LogFile = "C:\Bid-Master-System\logs\cgd\cgd_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"
python scripts\cgd_discovery.py --provinces "นครพนม" --max-calls 600 2>&1 | Tee-Object -FilePath $LogFile
git add data\winner_cache_bootstrap.json data\cgd_discovery_seen.json 2>>$LogFile
$staged = git diff --staged --name-only 2>>$LogFile
if ($staged) {
    git commit -m "chore: cgd-discovery local $(Get-Date -Format 'yyyy-MM-dd HH:mm') [skip ci]" 2>>$LogFile
    git push origin main 2>>$LogFile
}
Get-ChildItem "C:\Bid-Master-System\logs\cgd\cgd_*.log" | Sort-Object CreationTime | Select-Object -SkipLast 7 | Remove-Item -Force
