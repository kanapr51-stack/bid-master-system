# setup_etl_cron.ps1 - Schedule ETL sync every 30 min
#
# Run:
#   powershell -ExecutionPolicy Bypass -File scripts\setup_etl_cron.ps1

$TaskName = "BidMaster_ETL_Sync"
$ScriptDir = (Resolve-Path "$PSScriptRoot\..").Path
$ScriptPath = Join-Path $ScriptDir "scripts\Sebastian_ETL_Sync.py"
$LogDir = Join-Path $ScriptDir "logs\etl"

$pythonw = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
if ($pythonw) { $pythonw = $pythonw -replace "python\.exe$", "pythonw.exe" }
if (-not (Test-Path $pythonw)) {
    Write-Error "pythonw.exe not found"
    exit 1
}

Write-Host "Setting up scheduled task: $TaskName"

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
    -Argument "scripts\Sebastian_ETL_Sync.py" `
    -WorkingDirectory $ScriptDir

# Offset 18 min from other crons to stagger load
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(3) `
    -RepetitionInterval (New-TimeSpan -Minutes 30)

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -Hidden `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 5)

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive

Register-ScheduledTask -TaskName $TaskName `
    -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
    -Description "ETL Google Sheets -> Postgres every 30 min (Phase B)" | Out-Null

[Environment]::SetEnvironmentVariable("BMS_ETL_LOG_DIR", $LogDir, "User")

Write-Host ""
Write-Host "OK Task '$TaskName' created. First run in 3 min, then every 30 min."
Write-Host ""
Write-Host "Commands:"
Write-Host "  Run now:  schtasks /Run /TN $TaskName"
Write-Host "  Disable:  Disable-ScheduledTask -TaskName $TaskName"
Write-Host "  Delete:   schtasks /Delete /TN $TaskName /F"
