# setup_rss_cron.ps1 - Create Windows Scheduled Task for Sebastian RSS Scraper (every 30 min)
#
# Run:
#   powershell -ExecutionPolicy Bypass -File scripts\setup_rss_cron.ps1
#
# Remove:
#   schtasks /Delete /TN "BidMaster_RSS_Scraper" /F

$TaskName = "BidMaster_RSS_Scraper"
$ScriptDir = (Resolve-Path "$PSScriptRoot\..").Path
$BatPath = Join-Path $ScriptDir "scripts\run_rss_scraper.bat"

Write-Host "Setting up scheduled task: $TaskName"
Write-Host "  Script: $BatPath"

if (-not (Test-Path $BatPath)) {
    Write-Error "Not found: $BatPath"
    exit 1
}

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "  Removing existing task..."
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

$action = New-ScheduledTaskAction -Execute $BatPath -WorkingDirectory $ScriptDir
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes 30)
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 5)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive

Register-ScheduledTask -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Bid Master RSS Scraper - discovery + catalog growth (Phase 1)" | Out-Null

Write-Host ""
Write-Host "OK Task '$TaskName' created. First run in 1 min, then every 30 min."
Write-Host ""
Write-Host "Commands:"
Write-Host "  Status:    schtasks /Query /TN $TaskName /V /FO LIST"
Write-Host "  Run now:   schtasks /Run /TN $TaskName"
Write-Host "  Stop:      schtasks /End /TN $TaskName"
Write-Host "  Delete:    schtasks /Delete /TN $TaskName /F"
