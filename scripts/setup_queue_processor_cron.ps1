# setup_queue_processor_cron.ps1
# Schedule Universe B queue processor — runs 5 min after RSS scraper
#
# RSS scraper:      xx:22, xx:52 (every 30 min)
# Queue processor:  xx:27, xx:57 (every 30 min, staggered +5 min)
#
# Run:
#   powershell -ExecutionPolicy Bypass -File scripts\setup_queue_processor_cron.ps1

$TaskName  = "BidMaster_Queue_Processor"
$ScriptDir = (Resolve-Path "$PSScriptRoot\..").Path
$WrapperPS = Join-Path $ScriptDir "scripts\run_queue_processor.ps1"
$LogDir    = Join-Path $ScriptDir "logs\queue_processor"

Write-Host "Setting up scheduled task: $TaskName"
Write-Host "  Wrapper: $WrapperPS"
Write-Host "  Log dir: $LogDir"

if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
}

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "  Removing existing task..."
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

# Stagger: start 5 min from now, repeat every 30 min
# This naturally aligns ~5 min after RSS scraper each cycle
$startAt = (Get-Date).AddMinutes(5)

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -NonInteractive -WindowStyle Hidden -File `"$WrapperPS`"" `
    -WorkingDirectory $ScriptDir

$trigger = New-ScheduledTaskTrigger -Once -At $startAt `
    -RepetitionInterval (New-TimeSpan -Minutes 30)

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -Hidden `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 15) `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 3)

$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive

Register-ScheduledTask -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Universe B creation: consume rss_queue → new all_jobs rows → git push (local-only, credentials required)" | Out-Null

Write-Host ""
Write-Host "OK Task '$TaskName' created."
Write-Host "  First run: $($startAt.ToString('HH:mm')) (in 5 min)"
Write-Host "  Repeat:    every 30 min"
Write-Host "  Stagger:   ~5 min after BidMaster_RSS_Scraper (xx:22/xx:52 → xx:27/xx:57)"
Write-Host ""
Write-Host "Commands:"
Write-Host "  Status:    schtasks /Query /TN $TaskName /V /FO LIST"
Write-Host "  Run now:   schtasks /Run /TN $TaskName"
Write-Host "  Disable:   Disable-ScheduledTask -TaskName $TaskName"
Write-Host "  Delete:    schtasks /Delete /TN $TaskName /F"
Write-Host "  Log:       Get-Content logs\queue_processor\queue_processor_$(Get-Date -Format 'yyyyMMdd').log -Wait"
