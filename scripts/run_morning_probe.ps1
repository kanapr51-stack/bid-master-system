# run_morning_probe.ps1
# WAF re-engagement Phase R1 -- observation only, NOT production resume
#
# Protocol: canary -> if pass -> 1 unseen D0 -> STOP
# DO NOT re-enable Task Scheduler after this run
# DO NOT run additional IDs even if latency looks healthy
# DO NOT update api_state to HEALTHY
#
# Decision tree (see progress_log.md N+31):
#   canary fail                   -> Scenario C: silence 24-48h
#   canary pass + 1 ID < 600ms   -> Scenario A: log + STOP + wait +6h before R2
#   canary pass + 1 ID >= 3000ms -> Scenario B: extend silence, reduce probe freq
#
# "recovery probe itself changes future interaction-history"
# -> observe minimally, interpret carefully

$ScriptDir  = (Resolve-Path "$PSScriptRoot\..").Path
$LogDir     = Join-Path $ScriptDir "logs\morning_probe"
$LogFile    = Join-Path $LogDir ("probe_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".log")
$Python     = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
$CanaryID   = "69039439931"

if (-not $Python) { Write-Host "ERROR: python not found"; exit 1 }
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Force -Path $LogDir | Out-Null }

function Log($msg) {
    $line = "[$(Get-Date -Format 'HH:mm:ss')] $msg"
    Write-Host $line
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

Set-Location $ScriptDir

Log "=== Morning Probe Phase R1 start ==="
Log "Objective: OBSERVE regime, not resume production"
Log "Canary: $CanaryID"

# --- Step 1: Canary probe ---

$canaryStart = Get-Date
$probeResult = & $Python -c @"
import sys, time
sys.path.insert(0, 'scripts')
from process5_http_client import get_project_detail
t0 = time.time()
d = get_project_detail('$CanaryID')
ms = round((time.time()-t0)*1000)
print(('VALID' if d.get('valid') else 'INVALID') + f' latency_ms={ms}')
"@ 2>&1
$probeStr = ($probeResult -join '').Trim()
$canaryMs = if ($probeStr -match "latency_ms=(\d+)") { [int]$Matches[1] } else { -1 }
Log "Canary result: $probeStr"

if ($probeStr -notmatch "^VALID") {
    Log "SCENARIO C -- canary fail: probe lane degraded"
    Log "Action: silence 24-48h minimum, do not probe again today"
    Log "=== Probe done (Scenario C) ==="
    exit 0
}

Log "Canary passed ($canaryMs ms) -- selecting 1 unseen D0 for Phase R1"

# --- Step 2: Select 1 unseen D0 ID (deterministic) ---
# Strategy: most recent D0 item in rss_queue by queued_at

$targetId = & $Python -c @"
import json
from pathlib import Path
items = json.loads(Path('data/rss_queue.json').read_text(encoding='utf-8'))
d0 = [i for i in items if i.get('anounce_type') == 'D0']
d0.sort(key=lambda x: x.get('queued_at',''), reverse=True)
if d0:
    print(d0[0]['projectId'])
"@ 2>&1
$targetId = ($targetId -join '').Trim()

if (-not $targetId) {
    Log "No D0 items in rss_queue -- canary-only probe recorded"
    Log "=== Probe done (canary only) ==="
    exit 0
}

Log "Target ID: $targetId (most recent D0 by recency)"

# --- Step 3: Run exactly 1 ID ---

Log "Running 1 ID (limit=1) ..."
$batchStart = Get-Date
$result = & $Python "scripts\refresh_active_jobs.py" "--from-queue" "--workers" "1" "--limit" "1" 2>&1
$elapsedMs = [math]::Round(((Get-Date) - $batchStart).TotalMilliseconds)

$latencyAvgMs = -1
$processedCount = 0
foreach ($line in $result) {
    Log "  $line"
    if ($line -match "sparse row prepared") { $processedCount++ }
    if ($line -match "latency_ms avg=(\d+)") { $latencyAvgMs = [int]$Matches[1] }
}

Log "Elapsed: $elapsedMs ms | processed=$processedCount | latency_avg=$latencyAvgMs ms"

# --- Step 4: Classify scenario ---

$scenario = if ($latencyAvgMs -lt 0) {
    "unknown"
} elseif ($latencyAvgMs -lt 600) {
    "A_healthy"
} elseif ($latencyAvgMs -lt 1500) {
    "A_marginal"
} else {
    "B_degraded"
}

Log ""
Log "=== RESULT ==="
Log "Scenario : $scenario"
Log "Latency  : $latencyAvgMs ms (canary: $canaryMs ms)"
Log "Time     : $(Get-Date -Format 'HH:mm') (time-of-day covariate)"
Log ""

switch -Wildcard ($scenario) {
    "A_*" {
        Log "SCENARIO A -- regime may have recovered"
        Log "Interpretation: consistent with inactivity-linked recovery (NOT stable proven)"
        Log "Next action: WAIT +6h -> Phase R2 (3 IDs spaced)"
        Log "DO NOT resume scheduler. DO NOT run more IDs today."
    }
    "B_degraded" {
        Log "SCENARIO B -- 14h silence insufficient under current identity"
        Log "Interpretation: interaction-history persists beyond overnight silence"
        Log "Next action: extend silence further, reduce probe frequency"
        Log "DO NOT accept degraded operation. DO NOT tweak params."
    }
    default {
        Log "SCENARIO unknown -- inconclusive data"
        Log "Next action: wait and re-probe tomorrow morning"
    }
}

# --- Step 5: Append to probe history ---

$probeEntry = [PSCustomObject]@{
    probe_type        = "morning_probe_R1"
    probed_at         = (Get-Date -Format "yyyy-MM-ddTHH:mm:ss")
    silence_hours     = 14
    canary_latency_ms = $canaryMs
    canary_passed     = $true
    target_id         = $targetId
    processed_count   = $processedCount
    latency_avg_ms    = $latencyAvgMs
    elapsed_ms        = $elapsedMs
    scenario          = $scenario
}

$historyFile = Join-Path $ScriptDir "data\ingestion_run_history.json"
$history = @()
if (Test-Path $historyFile) {
    try { $history = Get-Content $historyFile -Raw | ConvertFrom-Json } catch {}
    if (-not $history) { $history = @() }
}
$history = @($history) + @($probeEntry)
if ($history.Count -gt 10) { $history = $history[-10..-1] }
$history | ConvertTo-Json | Set-Content $historyFile -Encoding UTF8
Log "Appended to ingestion_run_history.json"

Log ""
Log "=== Morning Probe Phase R1 done ==="
Log "REMINDER: Do NOT re-enable Task Scheduler until Phase R3+ validated"
