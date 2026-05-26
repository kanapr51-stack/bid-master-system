# run_queue_processor.ps1
# Universe B creation: consume rss_queue → new rows in all_jobs → git push
# Runs from local machine only (credentials/service_account.json required)

$ScriptDir = (Resolve-Path "$PSScriptRoot\..").Path
$LogDir    = Join-Path $ScriptDir "logs\queue_processor"
$LogFile   = Join-Path $LogDir ("queue_processor_" + (Get-Date -Format "yyyyMMdd") + ".log")
$Python    = (Get-Command python.exe -ErrorAction SilentlyContinue).Source

if (-not $Python) {
    exit 1
}

if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
}

function Log($msg) {
    $line = "[$(Get-Date -Format 'HH:mm:ss')] $msg"
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

Log "=== Queue Processor start ==="

# Step 1: git pull (get latest rss_queue from GHA/other commits)
Set-Location $ScriptDir
$pullOut = git pull --no-rebase origin main 2>&1
Log "git pull: $($pullOut -join ' | ')"

# Step 2: consume queue → new Universe B rows
Log "Running --from-queue --workers 3..."
$result = & $Python "scripts\refresh_active_jobs.py" "--from-queue" "--workers" "3" "--limit" "15" 2>&1
foreach ($line in $result) { Log $line }
$exitCode = $LASTEXITCODE
Log "exit code: $exitCode"

# Step 3: commit updated queue + winner cache
$gitAdd = git add data/rss_queue.json data/winner_cache_bootstrap.json data/rss_seen_ids.json 2>&1
Log "git add: $($gitAdd -join ' | ')"

$staged = git diff --staged --quiet 2>&1
if ($LASTEXITCODE -ne 0) {
    $ts = (Get-Date -Format "yyyy-MM-dd HH:mm")
    $commitOut = git commit -m "chore: queue-processor $ts [skip ci]" 2>&1
    Log "git commit: $($commitOut -join ' | ')"

    $pushOut = git push origin main 2>&1
    Log "git push: $($pushOut -join ' | ')"
} else {
    Log "nothing to commit"
}

Log "=== Queue Processor done ==="
