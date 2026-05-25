param(
    [string]$RunnerDir = "C:\actions-runner",
    [switch]$Remove
)

$TaskName = "BidMaster_GHRunner"

if ($Remove) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Removed task: $TaskName"
    exit 0
}

if (-not (Test-Path "$RunnerDir\run.cmd")) {
    Write-Error "Runner not found at $RunnerDir\run.cmd"
    exit 1
}

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Removing existing task..."
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

$action = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c run.cmd" `
    -WorkingDirectory $RunnerDir

$trigger = New-ScheduledTaskTrigger -AtLogOn

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -RestartCount 99 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Hours 0)

$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Highest

$task = New-ScheduledTask -Action $action -Trigger $trigger -Settings $settings -Principal $principal
Register-ScheduledTask -TaskName $TaskName -InputObject $task -Description "GHA runner bms" | Out-Null

Write-Host ""
Write-Host "OK Task created: $TaskName"
Write-Host ""
Write-Host "Run now:"
Write-Host "  Start-ScheduledTask -TaskName $TaskName"
