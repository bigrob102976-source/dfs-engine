# NFL M15 Phase 10 -- BigMoneyDFS_NFL_DK_Fetch_Worker's scheduled-task
# action. Runs the external NFL DraftKings fetch (scripts/
# fetch_nfl_slates.py) with the isolated nfl-web Railway service's
# production credentials injected via `railway run`, so this machine's
# real DraftKings network access keeps production's cache fresh --
# Railway's own egress IP can't reach DraftKings directly (see
# scripts/fetch_all_dfs_slates.py's docstring for the identical, already
# -documented MLB block this mirrors).
#
# Never touches MLB: only calls --service nfl-web (never dfs-engine),
# only writes under this repo's own dfs_input/nfl/ namespace (via the
# Python script) and this file's own log below.

Set-Location "D:\nfl-dfs-engine"

$logDir = "D:\nfl-dfs-engine\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logPath = Join-Path $logDir "nfl_dk_fetch_worker.log"

# Bound the log file's own growth -- keep the most recent ~2000 lines
# before appending this run's output.
if (Test-Path $logPath) {
    $existing = Get-Content $logPath -Tail 2000
    Set-Content -Path $logPath -Value $existing -Encoding utf8
}

$timestamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
Add-Content -Path $logPath -Value "`n=== $timestamp run start ===" -Encoding utf8

# Task Scheduler's own process context has a different PATH than an
# interactive shell, and does NOT have this repo's .venv activated --
# use absolute paths for both npx (this machine's real Node install)
# and python (this repo's own venv, which has boto3/ortools/etc.
# installed; the bare "python" on Task Scheduler's PATH does not).
# Both failure modes were observed on real natural firings before this
# fix: npx not found (first run), then boto3 missing under bare python
# (second run, after the first fix).
$npxPath = "C:\Users\taylo\AppData\Local\Programs\nodejs\npx.cmd"
$venvPython = "D:\nfl-dfs-engine\.venv\Scripts\python.exe"
$env:NODE_ENV = "production"

try {
    $output = & $npxPath --yes "@railway/cli" run --service nfl-web --environment production -- $venvPython scripts/fetch_nfl_slates.py 2>&1
    $exitCode = $LASTEXITCODE
} catch {
    $output = "WRAPPER_EXCEPTION: $_"
    $exitCode = 1
}

Add-Content -Path $logPath -Value $output -Encoding utf8
Add-Content -Path $logPath -Value "=== $timestamp run end (exit=$exitCode) ===" -Encoding utf8

exit $exitCode
