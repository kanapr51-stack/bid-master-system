# setup_cgd_local_cron.ps1 - Schedule CGD Discovery daily at 05:00 Thailand time (local machine)
#
# ต้องรัน local เพราะ opend.data.go.th block GHA IP (403 Forbidden)
#
# Run:
#   powershell -ExecutionPolicy Bypass -File scripts\setup_cgd_local_cron.ps1

$TaskName = "BidMaster_CGD_Discovery"
$ScriptDir = (Resolve-Path "$PSScriptRoot\..").Path
$WrapperPath = Join-Path $ScriptDir "scripts\_run_cgd_discovery.ps1"
$LogDir = Join-Path $ScriptDir "logs\cgd"

if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
}

# สร้าง wrapper script ที่รัน cgd_discovery.py + git push
@"
# _run_cgd_discovery.ps1 — wrapper รัน CGD discovery + commit + push
Set-Location "$ScriptDir"

`$LogFile = "$LogDir\cgd_`$(Get-Date -Format 'yyyyMMdd_HHmmss').log"

python scripts\cgd_discovery.py --provinces "นครพนม" --max-calls 600 2>&1 | Tee-Object -FilePath `$LogFile

# Commit + push ถ้ามีการเปลี่ยนแปลง
git add data\winner_cache_bootstrap.json data\cgd_discovery_seen.json data\cgd_discovery_cursor.json 2>>`$LogFile
`$staged = git diff --staged --name-only 2>>`$LogFile
if (`$staged) {
    git commit -m "chore: cgd-discovery local `$(Get-Date -Format 'yyyy-MM-dd HH:mm') [skip ci]" 2>>`$LogFile
    git push origin main 2>>`$LogFile
}

# เก็บ log 7 วัน
Get-ChildItem "$LogDir\cgd_*.log" | Sort-Object CreationTime | Select-Object -SkipLast 7 | Remove-Item -Force
"@ | Out-File -FilePath $WrapperPath -Encoding utf8

Write-Host "Setting up scheduled task: $TaskName"
Write-Host "  Wrapper: $WrapperPath"
Write-Host "  Log dir: $LogDir"

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "  Removing existing task..."
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -NonInteractive -File `"$WrapperPath`"" `
    -WorkingDirectory $ScriptDir

# 05:00 Thailand = 22:00 UTC (day before) — รัน local time 05:00
$trigger = New-ScheduledTaskTrigger -Daily -At "05:00"

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -Hidden `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 20) `
    -RestartCount 1 `
    -RestartInterval (New-TimeSpan -Minutes 5)

$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive

Register-ScheduledTask -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "CGD Discovery daily (local only — opend.data.go.th blocks GHA)" | Out-Null

Write-Host ""
Write-Host "OK Task '$TaskName' created. รันทุกวัน 05:00."
Write-Host ""
Write-Host "คำสั่ง:"
Write-Host "  รันเลย:   schtasks /Run /TN $TaskName"
Write-Host "  สถานะ:    schtasks /Query /TN '$TaskName' /V /FO LIST"
Write-Host "  ลบ:       schtasks /Delete /TN '$TaskName' /F"
Write-Host "  Log:      $LogDir"
