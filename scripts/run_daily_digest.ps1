# run_daily_digest.ps1
# BMS operational health digest — runs daily at 08:00 via Task Scheduler

$ScriptDir = (Resolve-Path "$PSScriptRoot\..").Path
$LogDir    = Join-Path $ScriptDir "logs\digest"
$LogFile   = Join-Path $LogDir ("digest_" + (Get-Date -Format "yyyyMMdd") + ".log")
$BootLog   = Join-Path $ScriptDir "logs\boot_trace.log"
$Python    = (Get-Command python.exe -ErrorAction SilentlyContinue).Source

if (-not $Python) {
    Add-Content -Path $BootLog -Value "$(Get-Date -Format 'yyyy-MM-ddTHH:mm:ss') DAILY_DIGEST BOOT_FAIL python_not_found" -Encoding UTF8
    exit 1
}
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Force -Path $LogDir | Out-Null }

function Log($msg) {
    $line = "[$(Get-Date -Format 'HH:mm:ss')] $msg"
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

Set-Location $ScriptDir
Add-Content -Path $BootLog -Value "$(Get-Date -Format 'yyyy-MM-ddTHH:mm:ss') DAILY_DIGEST START pid=$PID" -Encoding UTF8
Log "=== Daily Digest wrapper start ==="

$result = & $Python "scripts\Sebastian_Daily_Digest.py" 2>&1
foreach ($line in $result) { Log $line }
$pyExit = $LASTEXITCODE

Log "exit_code=$pyExit"
Log "=== Daily Digest wrapper done ==="
