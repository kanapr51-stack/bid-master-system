# run_queue_processor.ps1
# Universe B creation: consume rss_queue → new rows in all_jobs → git push
# Runs from local machine only (credentials/service_account.json required)
#
# State machine: HEALTHY → process 15 | BLOCKED → skip (preserve local IP trust)
# Block persistence: canary fail → +30min cooldown | HTML rejection → +2h

$ScriptDir  = (Resolve-Path "$PSScriptRoot\..").Path
$LogDir     = Join-Path $ScriptDir "logs\queue_processor"
$LogFile    = Join-Path $LogDir ("queue_processor_" + (Get-Date -Format "yyyyMMdd") + ".log")
$StateFile  = Join-Path $ScriptDir "data\api_ingestion_state.json"
$Python     = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
$CanaryID   = "69039439931"

if (-not $Python) { exit 1 }
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Force -Path $LogDir | Out-Null }

function Log($msg) {
    $line = "[$(Get-Date -Format 'HH:mm:ss')] $msg"
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

function Read-State {
    if (Test-Path $StateFile) {
        try { return Get-Content $StateFile -Raw | ConvertFrom-Json }
        catch {}
    }
    return $null
}

function Write-State($apiState, $blockedUntil, $lastCanarySuccess, $safeLimit) {
    $obj = @{
        api_state            = $apiState
        blocked_until        = $blockedUntil
        last_canary_success  = $lastCanarySuccess
        safe_limit_current   = $safeLimit
        updated_at           = (Get-Date -Format "yyyy-MM-ddTHH:mm:ss")
    }
    $obj | ConvertTo-Json | Set-Content $StateFile -Encoding UTF8
}

Log "=== Queue Processor start ==="

# Step 1: Check persistent block state
$state = Read-State
if ($state -and $state.blocked_until) {
    $blockedUntil = [datetime]::Parse($state.blocked_until)
    if ((Get-Date) -lt $blockedUntil) {
        Log "BLOCKED (persisted) — blocked_until=$($state.blocked_until) — skipping cycle"
        Log "=== Queue Processor skipped (BLOCKED) ==="
        exit 0
    }
}

# Step 2: git pull
Set-Location $ScriptDir
$pullOut = git pull --no-rebase origin main 2>&1
Log "git pull: $($pullOut -join ' | ')"

# Step 3: Preflight canary probe
Log "Preflight probe: $CanaryID ..."
$probeResult = & $Python -c "
import sys
sys.path.insert(0, 'scripts')
from process5_http_client import get_project_detail
d = get_project_detail('$CanaryID')
print('VALID' if d.get('valid') else 'INVALID')
" 2>&1
$probeStr = $probeResult -join ''
Log "Probe: $probeStr"

if ($probeStr -notmatch "VALID") {
    $blockedUntil = (Get-Date).AddMinutes(30).ToString("yyyy-MM-ddTHH:mm:ss")
    $lastSuccess  = if ($state) { $state.last_canary_success } else { "" }
    Write-State "BLOCKED" $blockedUntil $lastSuccess 15
    Log "BLOCKED — canary fail. blocked_until=$blockedUntil. Aborting."
    Log "=== Queue Processor aborted (BLOCKED) ==="
    exit 0
}

# Canary passed
$lastSuccess  = (Get-Date -Format "yyyy-MM-ddTHH:mm:ss")
$runStartedAt = $lastSuccess
Write-State "HEALTHY" "" $lastSuccess 15
Log "HEALTHY — proceeding with batch (limit=15)"

# Step 4: consume queue → new Universe B rows
$result = & $Python "scripts\refresh_active_jobs.py" "--from-queue" "--workers" "3" "--limit" "15" 2>&1
foreach ($line in $result) { Log $line }
$pyExit = $LASTEXITCODE
Log "exit code: $pyExit"

# Parse time-to-block telemetry from output
$processedCount = 0
$firstInvalidAt = ""
foreach ($line in $result) {
    if ($line -match "sparse row prepared") { $processedCount++ }
    if ($line -match "detail ไม่ valid" -and $firstInvalidAt -eq "") {
        $firstInvalidAt = (Get-Date -Format "yyyy-MM-ddTHH:mm:ss")
    }
}

# Detect mid-batch HTML WAF block → extend cooldown to 2h
$logContent = Get-Content $LogFile -Raw
$earlyStop  = $logContent -match "EARLY STOP"
if ($earlyStop) {
    $blockedUntil = (Get-Date).AddHours(2).ToString("yyyy-MM-ddTHH:mm:ss")
    Write-State "BLOCKED" $blockedUntil $lastSuccess 15
    Log "Mid-batch EARLY STOP — extended block 2h. blocked_until=$blockedUntil"
}

# Log time-to-block envelope data
$envelopeEntry = @{
    run_started_at         = $runStartedAt
    first_invalid_at       = $firstInvalidAt
    processed_before_stop  = $processedCount
    batch_limit            = 15
    early_stop             = $earlyStop
} | ConvertTo-Json -Compress
Log "envelope: $envelopeEntry"

# Step 5: export queue health snapshot
$healthOut = & $Python "scripts\queue_health.py" 2>&1
Log "queue_health: $($healthOut -join '')"

# Step 6: commit updated queue + winner cache + health snapshot
$gitAdd = git add data/rss_queue.json data/winner_cache_bootstrap.json data/rss_seen_ids.json data/api_ingestion_state.json data/queue_health_snapshot.json 2>&1
Log "git add: $($gitAdd -join ' | ')"

$null = git diff --staged --quiet 2>&1
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
