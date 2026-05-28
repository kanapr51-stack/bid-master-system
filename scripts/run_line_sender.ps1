# run_line_sender.ps1
# LINE notification delivery worker wrapper
# Runs every 1 min via Task Scheduler (BidMaster_LINE_Sender)
#
# Architecture plane 3 of 3:
#   RSS Scraper  → rss_queue.json (discovery log)
#   RSS Notifier → classify province + confidence → notification_queue
#   LINE Sender  → deliver via LINE push API                            ← THIS
#
# Enable Task Scheduler ONLY after first manual live send is validated.
# Pilot success checklist before enabling:
#   ✅ no duplicates across reruns
#   ✅ no false-positive province
#   ✅ human-readable in <3 sec scan
#   ✅ sender survives restart/retry
#   ✅ queue converges cleanly
#   ✅ delivery_log consistent with queue state

$ScriptDir = (Resolve-Path "$PSScriptRoot\..").Path
$LogDir    = Join-Path $ScriptDir "logs\line_sender"
$LogFile   = Join-Path $LogDir ("sender_" + (Get-Date -Format "yyyyMMdd") + ".log")
$Python    = (Get-Command python.exe -ErrorAction SilentlyContinue).Source

if (-not $Python) { exit 1 }
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Force -Path $LogDir | Out-Null }

function Log($msg) {
    $line = "[$(Get-Date -Format 'HH:mm:ss')] $msg"
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

Set-Location $ScriptDir
Log "=== LINE Sender wrapper start ==="

$result = & $Python "scripts\Sebastian_LINE_Sender.py" 2>&1
foreach ($line in $result) { Log $line }
$pyExit = $LASTEXITCODE

Log "exit_code=$pyExit"
Log "=== LINE Sender wrapper done ==="
