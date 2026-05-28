# setup_dashboard_cron.ps1 - Schedule dashboard refresh every 30 min
#
# Run:
#   powershell -ExecutionPolicy Bypass -File scripts\setup_dashboard_cron.ps1

$TaskName = "BidMaster_Dashboard_Refresh"
$ScriptDir = (Resolve-Path "$PSScriptRoot\..").Path
$ScriptPath = Join-Path $ScriptDir "scripts\Sebastian_Dashboard_Refresh.py"
$LogDir = Join-Path $ScriptDir "logs\dashboard"

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

if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
}

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "  Removing existing task..."
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

$action = New-ScheduledTaskAction `
    -Execute $pythonw `
    -Argument "scripts\Sebastian_Dashboard_Refresh.py" `
    -WorkingDirectory $ScriptDir

# Stagger: start 15 min OFFSET from RSS cron (RSS runs xx:22, xx:52 → dashboard runs xx:07, xx:37)
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) `
    -RepetitionInterval (New-TimeSpan -Minutes 30)

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -Hidden `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 2)

$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive

Register-ScheduledTask -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Refresh dashboard snapshot + upload to Vercel Blob every 30 min" | Out-Null

[Environment]::SetEnvironmentVariable("BMS_DASHBOARD_LOG_DIR", $LogDir, "User")
Write-Host "  Set BMS_DASHBOARD_LOG_DIR = $LogDir"

Write-Host ""
Write-Host "OK Task '$TaskName' created. First run in 2 min, then every 30 min."
Write-Host ""
Write-Host "Commands:"
Write-Host "  Status:    schtasks /Query /TN $TaskName /V /FO LIST"
Write-Host "  Run now:   schtasks /Run /TN $TaskName"
Write-Host "  Disable:   Disable-ScheduledTask -TaskName $TaskName"
Write-Host "  Delete:    schtasks /Delete /TN $TaskName /F"
