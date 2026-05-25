$TaskName = "BidMaster_GHRunner"

schtasks /Delete /TN $TaskName /F 2>$null

schtasks /Create /TN $TaskName `
    /TR "cmd /k C:\actions-runner\run.cmd" `
    /SC ONLOGON `
    /F

if ($LASTEXITCODE -eq 0) {
    Write-Host "OK Scheduled Task created: $TaskName"
    Write-Host "Runner will auto-start on every Windows logon."
    Write-Host ""
    Write-Host "Start now:"
    Write-Host "  schtasks /Run /TN $TaskName"
} else {
    Write-Host "ERROR creating task (exit $LASTEXITCODE)"
}
