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
# ---- Detach from console CTRL+C / CTRL+BREAK (2026-09-13) -------------
# Both DFS workers run as Task Scheduler tasks with LogonType=Interactive,
# which executes them inside the logged-on console session. Console
# control events are delivered to every process attached to that console,
# so unrelated activity in the same session (an interactive shell killing
# a child, a terminal/agent session reaping background jobs) could
# terminate a mid-flight worker. That is the long-unexplained failure
# recorded against the MLB worker as exit 3221225786 / 0xC000013A
# (STATUS_CONTROL_C_EXIT) "with zero diagnostic output beyond starting" --
# both tasks were observed returning exactly that code on 2026-09-13.
#
# SetConsoleCtrlHandler(NULL, TRUE) makes THIS process ignore CTRL_C_EVENT
# outright, and the flag is inherited by child processes -- so the Railway
# CLI and python child this wrapper spawns become immune too. The proper
# fix is running the task non-interactively (LogonType=S4U, "run whether
# user is logged on or not"), but that requires administrator rights this
# task's account does not have; this achieves the same isolation for the
# CTRL_C case without elevation. Failure to apply is never fatal: the
# worker still runs, just as interruptible as it was before.
try {
    if (-not ("Win32.ConsoleCtl" -as [type])) {
        Add-Type -Namespace Win32 -Name ConsoleCtl -MemberDefinition @"
[DllImport("kernel32.dll", SetLastError=true)]
public static extern bool SetConsoleCtrlHandler(IntPtr handler, bool add);
"@ -ErrorAction Stop
    }
    [void][Win32.ConsoleCtl]::SetConsoleCtrlHandler([IntPtr]::Zero, $true)
} catch {
    # Non-fatal: proceed without CTRL_C immunity rather than skip the run.
}

$logPath = Join-Path $logDir "nfl_dk_fetch_worker.log"

# Bound the log file's own growth. This used to read-then-Set-Content the
# log on EVERY firing, which is a truncate-and-rewrite of the whole file:
# when a run was killed partway through that rewrite (observed 2026-09-13,
# Task Scheduler result 0xC000013A / STATUS_CONTROL_C_EXIT -- the same
# unexplained kill documented for the MLB worker), the log was left
# destroyed, taking ~90 runs of diagnostic history with it and making the
# worker impossible to verify. Now: only rewrite when the file is actually
# oversized, and stage it through a temp file + atomic Move so a kill at
# any instant leaves either the old log or the new one, never a truncated
# one.
$LogMaxLines  = 5000
$LogKeepLines = 2000
if (Test-Path $logPath) {
    try {
        $lineCount = (Get-Content $logPath -ReadCount 0 | Measure-Object -Line).Lines
        if ($lineCount -gt $LogMaxLines) {
            $tmp = "$logPath.trim.tmp"
            Get-Content $logPath -Tail $LogKeepLines | Set-Content -Path $tmp -Encoding utf8
            Move-Item -Path $tmp -Destination $logPath -Force
        }
    } catch {
        # Never let log maintenance stop the actual fetch.
    }
}

$timestamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
Add-Content -Path $logPath -Value "`n=== $timestamp run start ===" -Encoding utf8

# ---- MLB-active guard + starvation escape hatch (2026-09-13) ----------
# Every NFL firing that overlapped an active MLB worker cycle stalled at
# zero output until the timeout; every run taken while MLB was idle
# finished in ~37-39s. MLB's cycle is now long (DK ~90s + research up to
# ~600s + Vegas up to 240s), so overlap is the common case rather than the
# rare one. Instead of racing it, defer: skip this firing cleanly and let
# the next scheduled one retry. This changes NOTHING about MLB -- it only
# READS MLB's state, never its files, schedule or configuration.
#
# Detection uses process/task signals, never timestamps: the scheduled
# task's own State, plus any live MLB wrapper process or Railway CLI
# invocation against the MLB service. A status-file mtime would go stale
# or lie outright if a run died mid-write; a running process cannot.
$statusPath = Join-Path $logDir "nfl_dk_fetch_worker_status.json"
$priorStatus = $null
if (Test-Path $statusPath) {
    try { $priorStatus = Get-Content $statusPath -Raw | ConvertFrom-Json } catch { $priorStatus = $null }
}

function Test-MlbWorkerActive {
    try {
        $t = Get-ScheduledTask -TaskName 'BigMoneyDFS_MLB_DK_Fetch_Worker' -ErrorAction Stop
        if ($t.State -eq 'Running') { return $true }
    } catch { }
    try {
        $hit = Get-CimInstance Win32_Process -Filter "Name='powershell.exe' OR Name='railway.exe'" -ErrorAction SilentlyContinue |
               Where-Object { $_.CommandLine -and ($_.CommandLine -match 'run_mlb_dk_fetch_worker' -or $_.CommandLine -match '--service +dfs-engine') }
        if ($hit) { return $true }
    } catch { }
    return $false
}

# Escape hatch: NFL's served pools go stale at nfl/pool_cache.py's 2h
# ceiling, so deferring indefinitely would be its own outage. Past 90
# minutes with no successful publish, take the overlap risk instead.
$NflMaxPublishAgeMinutes = 90
$publishAgeMinutes = $null
if ($priorStatus -and $priorStatus.last_success_at) {
    try { $publishAgeMinutes = ((Get-Date).ToUniversalTime() - [datetime]::Parse($priorStatus.last_success_at).ToUniversalTime()).TotalMinutes } catch { $publishAgeMinutes = $null }
}

$forcedRefresh = $false
if (Test-MlbWorkerActive) {
    if ($null -eq $publishAgeMinutes) {
        # No recorded successful publish yet -- deferring on that basis
        # would never resolve, so proceed and establish a baseline.
        $forcedRefresh = $true
        Add-Content -Path $logPath -Value "NFL_FORCED_REFRESH_AGE_LIMIT no recorded successful publish yet -- proceeding despite active MLB worker" -Encoding utf8
    } elseif ($publishAgeMinutes -ge $NflMaxPublishAgeMinutes) {
        $forcedRefresh = $true
        Add-Content -Path $logPath -Value ("NFL_FORCED_REFRESH_AGE_LIMIT last successful publish {0:N1} minutes ago (limit {1}) -- proceeding despite active MLB worker" -f $publishAgeMinutes, $NflMaxPublishAgeMinutes) -Encoding utf8
    } else {
        Add-Content -Path $logPath -Value ("NFL_DEFERRED_MLB_ACTIVE MLB worker active; last successful NFL publish {0:N1} minutes ago (limit {1}). Skipping this firing; next scheduled firing retries." -f $publishAgeMinutes, $NflMaxPublishAgeMinutes) -Encoding utf8
        Add-Content -Path $logPath -Value "=== $timestamp run end (exit=0, deferred) ===" -Encoding utf8
        $deferredSuccess = $null
        if ($priorStatus) { $deferredSuccess = $priorStatus.last_success_at }
        $deferred = [ordered]@{
            last_run_at     = (Get-Date).ToUniversalTime().ToString("o")
            last_outcome    = "deferred_mlb_active"
            last_success_at = $deferredSuccess
        }
        try { $deferred | ConvertTo-Json | Set-Content -Path $statusPath -Encoding utf8 } catch { }
        exit 0
    }
}
# ---- end guard --------------------------------------------------------

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

# Resolve the Railway CLI BINARY: a real install on PATH first, else
# whichever npx cache entry actually holds it (that cache directory name
# is a content hash, so it is never hardcoded). Invoking the binary skips
# the four extra processes npx inserts ahead of it (npx.cmd -> node ->
# cmd -> node) and its PATH-based shim resolution -- Task Scheduler hands
# this task a ~522-character PATH, far shorter than an interactive
# shell's. npx remains a logged fallback so a cleared cache degrades to
# the old behaviour rather than to no fetch at all.
$railwayExe = $null
$onPath = Get-Command railway.exe -ErrorAction SilentlyContinue
if ($onPath) { $railwayExe = $onPath.Source }
if (-not $railwayExe) {
    $npxRoot = Join-Path $env:LOCALAPPDATA "npm-cache\_npx"
    $cand = Get-ChildItem $npxRoot -Directory -ErrorAction SilentlyContinue |
            ForEach-Object { Join-Path $_.FullName "node_modules\@railway\cli\bin\railway.exe" } |
            Where-Object { Test-Path $_ } | Select-Object -First 1
    if ($cand) { $railwayExe = $cand }
}

# BOUNDED INVOCATION (2026-09-13). The previous `& $npxPath ... 2>&1`
# call had NO timeout and no async stream draining, so anything blocking
# inside the Railway CLI blocked this wrapper forever: the log showed
# "run start" with no matching "run end" for every firing from
# 2026-09-13T02:12Z onward, Task Scheduler reported
# SCHED_S_TASK_TERMINATED (0x00041316) at the old PT3M limit, and NFL's
# cached pools aged past nfl/pool_cache.py's 2h stale ceiling until
# /api/nfl/data returned 502 for every DraftGroup.
#
# Observed failure mode, stated without inferring a cause: every firing
# that overlapped an active MLB worker cycle produced ZERO bytes on both
# stdout and stderr until the timeout, while the identical command run
# while MLB was idle completed in ~37-39s. Measured in this task's own
# context each layer on its own is healthy and fast (cmd ~29ms, python
# ~66ms, railway.exe --version ~28ms, DNS ~122ms), so the stall is not
# any one of them. The guard above avoids the overlap rather than
# asserting a mechanism that has not been proven.
#
# Same shape as the MLB worker's Invoke-Stage (commit d87101f): redirect
# both streams, drain them asynchronously so a full pipe buffer can
# never deadlock the child, and bound the wait. --project is now passed
# explicitly (MLB already did) so resolution never depends on the
# per-directory link in the shared config this stage contends over.

$RailwayProjectId = "3f0a4e42-22a4-4ebd-8e7f-2006261c5393"
$StageTimeoutSeconds = 240

$stdout = New-Object System.Text.StringBuilder
$stderr = New-Object System.Text.StringBuilder
$proc = $null
$outEvt = $null
$errEvt = $null
$timedOut = $false

try {
    # Invoke the Railway CLI BINARY directly instead of going through
    # `npx --yes @railway/cli`. Measured in this task's own context on
    # 2026-09-13 (see the PROBE lines above): cmd 29ms, python 66ms,
    # railway.exe --version 28ms, DNS 122ms -- every layer is healthy and
    # fast. Only the npx route hung, and it hung at 0 bytes of output for
    # the full 240s on every firing, while the identical command finished
    # in ~37-39s from an ordinary shell.
    #
    # npx inserts four extra processes (npx.cmd -> node -> cmd -> node)
    # ahead of the binary and resolves its `railway` shim through PATH --
    # and Task Scheduler hands this task a 522-character PATH, far shorter
    # than an interactive shell's. Calling the binary removes that whole
    # failure surface. npx stays as a last-resort fallback so a cleared
    # npx cache degrades to the old behaviour rather than to no fetch.
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    if ($railwayExe -and (Test-Path $railwayExe)) {
        $psi.FileName = $railwayExe
        $psi.Arguments = "run --project $RailwayProjectId --service nfl-web --environment production -- `"$venvPython`" -u scripts/fetch_nfl_slates.py"
    } else {
        Add-Content -Path $logPath -Value "WARN railway.exe not found; falling back to npx" -Encoding utf8
        $psi.FileName = $npxPath
        $psi.Arguments = "--yes `"@railway/cli`" run --project $RailwayProjectId --service nfl-web --environment production -- `"$venvPython`" -u scripts/fetch_nfl_slates.py"
    }
    $psi.WorkingDirectory = (Split-Path -Parent $PSScriptRoot)
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    # Deliberately NOT setting RedirectStandardInput or CreateNoWindow.
    # Both were tried on 2026-09-13 and both are wrong here: with stdin
    # redirected-then-closed and no console allocated, this exact command
    # (which completes in ~37s when run normally) never returned inside
    # 240s under Task Scheduler, so every firing hit STAGE_TIMEOUT and NFL
    # published nothing. The MLB worker's Invoke-Stage -- the pattern this
    # is meant to mirror, and the one proven in production -- sets only
    # UseShellExecute=false plus the two output redirects. Match it exactly.

    $proc = New-Object System.Diagnostics.Process
    $proc.StartInfo = $psi
    $outEvt = Register-ObjectEvent -InputObject $proc -EventName OutputDataReceived -MessageData $stdout -Action {
        if ($null -ne $EventArgs.Data) { [void]$Event.MessageData.AppendLine($EventArgs.Data) }
    }
    $errEvt = Register-ObjectEvent -InputObject $proc -EventName ErrorDataReceived -MessageData $stderr -Action {
        if ($null -ne $EventArgs.Data) { [void]$Event.MessageData.AppendLine($EventArgs.Data) }
    }

    [void]$proc.Start()
    $proc.BeginOutputReadLine()
    $proc.BeginErrorReadLine()

    Add-Content -Path $logPath -Value ("TRACE {0} process started pid={1}" -f (Get-Date).ToUniversalTime().ToString("HH:mm:ss"), $proc.Id) -Encoding utf8
    $waited = 0
    while (-not $proc.HasExited -and $waited -lt $StageTimeoutSeconds) {
        [void]$proc.WaitForExit(15000)
        $waited += 15
        if (-not $proc.HasExited) {
            Add-Content -Path $logPath -Value ("TRACE {0} still running at {1}s; stdout={2}B stderr={3}B" -f (Get-Date).ToUniversalTime().ToString("HH:mm:ss"), $waited, $stdout.Length, $stderr.Length) -Encoding utf8
        }
    }
    if ($proc.HasExited) {
        $exitCode = $proc.ExitCode
        Add-Content -Path $logPath -Value ("TRACE {0} exited code={1} after {2}s" -f (Get-Date).ToUniversalTime().ToString("HH:mm:ss"), $exitCode, $waited) -Encoding utf8
    } else {
        $timedOut = $true
        $exitCode = 1
        # Windows PowerShell 5.1's Process.Kill() takes NO arguments --
        # Kill($true) ("kill entire process tree") is .NET Core 3.0+ only, so
        # that call threw and the catch killed only the top-level cmd.exe,
        # orphaning the whole npx -> node -> cmd -> node -> railway.exe ->
        # cmd -> python descendant chain. Ten such trees were found alive at
        # once on 2026-09-13, one per timed-out firing going back ~45 minutes,
        # each still holding a live DraftKings fetch and the shared Railway
        # credential store -- which made every subsequent run slower until it
        # timed out too, a feedback loop that turned one stall into a total
        # NFL outage. taskkill /T /F is the 5.1-correct way to kill the tree.
        try { & taskkill.exe /PID $proc.Id /T /F 2>&1 | Out-Null } catch {}
        try { if (-not $proc.HasExited) { $proc.Kill() } } catch {}
        try { [void]$proc.WaitForExit(15000) } catch {}
    }
} catch {
    $exitCode = 1
    [void]$stderr.AppendLine("WRAPPER_EXCEPTION: $($_.Exception.GetType().FullName): $($_.Exception.Message)")
    [void]$stderr.AppendLine($_.ScriptStackTrace)
} finally {
    if ($outEvt) { Unregister-Event -SourceIdentifier $outEvt.Name -ErrorAction SilentlyContinue }
    if ($errEvt) { Unregister-Event -SourceIdentifier $errEvt.Name -ErrorAction SilentlyContinue }
    if ($proc)   { try { $proc.Dispose() } catch {} }
}

$output = $stdout.ToString() + $stderr.ToString()
if ($timedOut) {
    $output = $output + ("`nSTAGE_TIMEOUT: child process exceeded {0}s without producing output; " -f $StageTimeoutSeconds) +
              "process tree killed. This run published nothing and the next firing retries."
}

Add-Content -Path $logPath -Value $output -Encoding utf8
Add-Content -Path $logPath -Value "=== $timestamp run end (exit=$exitCode) ===" -Encoding utf8

# A "successful publish" means the fetch actually emitted its result
# document with at least one DraftGroup saved -- NOT merely exit 0. The
# python script exits 1 whenever ANY discovered DraftGroup fails, which is
# the steady state while DraftGroup 153109 returns SCHEMA_CHANGED even
# though the other five published fine.
$published = (($output -match 'slates_discovered') -and ($output -match '"status": "ok"'))
$successAt = $null
if ($published) { $successAt = (Get-Date).ToUniversalTime().ToString("o") }
elseif ($priorStatus) { $successAt = $priorStatus.last_success_at }
$outcome = "error"
if ($published) { $outcome = "published" } elseif ($timedOut) { $outcome = "timeout" }
$newStatus = [ordered]@{
    last_run_at     = (Get-Date).ToUniversalTime().ToString("o")
    last_outcome    = $outcome
    last_exit_code  = $exitCode
    forced_refresh  = $forcedRefresh
    last_success_at = $successAt
}
try { $newStatus | ConvertTo-Json | Set-Content -Path $statusPath -Encoding utf8 } catch { }

exit $exitCode
