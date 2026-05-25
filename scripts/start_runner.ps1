$runner = "C:\actions-runner\run.cmd"
if (-not (Test-Path $runner)) {
    Write-Host "ERROR: $runner not found"
    exit 1
}
Write-Host "Starting GitHub Actions runner in new window..."
Start-Process "cmd.exe" -ArgumentList "/k", $runner -WorkingDirectory "C:\actions-runner"
Start-Sleep 5
$proc = Get-Process "Runner.Listener" -ErrorAction SilentlyContinue
if ($proc) {
    Write-Host "Runner.Listener PID=$($proc.Id) - RUNNING OK"
} else {
    Write-Host "Runner started (window opened) - check the new window for status"
}
