# run_rss_notifier.ps1
# RSS → notification classifier/enqueuer wrapper
# Runs every 5 min via Task Scheduler (BidMaster_RSS_Notifier)
#
# Architecture plane 2 of 3:
#   RSS Scraper  → rss_queue.json (discovery log)
#   RSS Notifier → classify province + confidence → notification_queue  ← THIS
#   LINE Sender  → deliver via LINE push API
#
# Design: no state machine needed (idempotency handled by projects_seen INSERT OR IGNORE)
# Enable Task Scheduler ONLY after first manual live send is validated.

$ScriptDir = (Resolve-Path "$PSScriptRoot\..").Path
$LogDir    = Join-Path $ScriptDir "logs\rss_notifier"
$LogFile   = Join-Path $LogDir ("notifier_" + (Get-Date -Format "yyyyMMdd") + ".log")
$BootLog   = Join-Path $ScriptDir "logs\boot_trace.log"
$Python    = (Get-Command python.exe -ErrorAction SilentlyContinue).Source

if (-not $Python) {
    Add-Content -Path $BootLog -Value "$(Get-Date -Format 'yyyy-MM-ddTHH:mm:ss') RSS_NOTIFIER BOOT_FAIL python_not_found" -Encoding UTF8
    exit 1
}
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Force -Path $LogDir | Out-Null }

function Log($msg) {
    $line = "[$(Get-Date -Format 'HH:mm:ss')] $msg"
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

Set-Location $ScriptDir
Add-Content -Path $BootLog -Value "$(Get-Date -Format 'yyyy-MM-ddTHH:mm:ss') RSS_NOTIFIER START pid=$PID cwd=$ScriptDir" -Encoding UTF8
Log "=== RSS Notifier wrapper start ==="

$result = & $Python "scripts\Sebastian_RSS_Notifier.py" 2>&1
foreach ($line in $result) { Log $line }
$pyExit = $LASTEXITCODE

Log "exit_code=$pyExit"
Log "=== RSS Notifier wrapper done ==="
