# setup_rss_cron.ps1 - Create Windows Scheduled Task for Sebastian RSS Scraper (every 30 min)
#
# Run:
#   powershell -ExecutionPolicy Bypass -File scripts\setup_rss_cron.ps1
#
# Remove:
#   schtasks /Delete /TN "BidMaster_RSS_Scraper" /F

$TaskName = "BidMaster_RSS_Scraper"
$ScriptDir = (Resolve-Path "$PSScriptRoot\..").Path
$ScriptPath = Join-Path $ScriptDir "scripts\Sebastian_RSS_Scraper.py"
$LogDir = Join-Path $ScriptDir "logs\rss"

# Find pythonw.exe (windowless)
$pythonw = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
if ($pythonw) { $pythonw = $pythonw -replace "python\.exe$", "pythonw.exe" }
if (-not (Test-Path $pythonw)) {
    Write-Error "pythonw.exe not found"
    exit 1
}

Write-Host "Setting up scheduled task: $TaskName"
Write-Host "  pythonw: $pythonw"
Write-Host "  Script: $ScriptPath"
Write-Host "  Log dir: $LogDir"

# Ensure log dir
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
}

# Remove existing
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "  Removing existing task..."
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

# Action: pythonw.exe directly (no .bat wrapper → no CMD window)
# Pass BMS_RSS_LOG_DIR via env to make script write its own log file
$action = New-ScheduledTaskAction `
    -Execute $pythonw `
    -Argument "scripts\Sebastian_RSS_Scraper.py --queue --stage rotate" `
    -WorkingDirectory $ScriptDir

$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes 30)

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -Hidden `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 5)

$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive

$task = Register-ScheduledTask -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Bid Master RSS Scraper - discovery + catalog growth (Phase 1)"

# Inject env var BMS_RSS_LOG_DIR by editing task XML (Register-ScheduledTask doesn't expose env)
# Workaround: keep log path inside the script via constant
# (We'll set the env in setup_rss_cron.ps1 by exporting it system-wide once - alternative: pass --log-dir)
# Simpler: do nothing here, log path handled inside script
# The script reads BMS_RSS_LOG_DIR — if not set, falls back to stdout (lost when hidden)
# So we need to ensure env is set when task runs:

# Set BMS_RSS_LOG_DIR as USER env (persists across sessions)
[Environment]::SetEnvironmentVariable("BMS_RSS_LOG_DIR", $LogDir, "User")
Write-Host "  Set BMS_RSS_LOG_DIR env (user) = $LogDir"

Write-Host ""
Write-Host "OK Task '$TaskName' created. First run in 1 min, then every 30 min."
Write-Host "  → pythonw.exe direct (no CMD window) + Hidden flag"
Write-Host ""
Write-Host "Commands:"
Write-Host "  Status:    schtasks /Query /TN $TaskName /V /FO LIST"
Write-Host "  Run now:   schtasks /Run /TN $TaskName"
Write-Host "  Stop:      schtasks /End /TN $TaskName"
Write-Host "  Delete:    schtasks /Delete /TN $TaskName /F"
