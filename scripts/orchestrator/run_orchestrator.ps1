<#
.SYNOPSIS
Big Money DFS centralized refresh orchestrator.

.DESCRIPTION
Replaces the fragile one-Windows-Task-per-sport scheduling design
(BigMoneyDFS_MLB_DK_Fetch_Worker / BigMoneyDFS_NFL_DK_Fetch_Worker) with
ONE supervisor process that launches each sport's EXISTING, unmodified
production wrapper script (run_mlb_dk_fetch_worker.ps1 /
run_nfl_dk_fetch_worker.ps1) on its own schedule, tracks per-sport state,
enforces a hard outer timeout with real process-tree cleanup, and retries
failures sooner than successful cycles -- without ever letting one
sport's slow or hung job block another's.

This script does NOT reimplement DK ingestion, identity resolution,
projections, Vegas, ownership, or persistence. It only decides WHEN to
launch each sport's already-verified pipeline and supervises the OS
process that runs it. Every sport is launched as an independent,
non-blocking child process (System.Diagnostics.Process), so true
concurrency -- not cooperative scheduling inside one script -- is what
prevents cross-sport starvation.

SUCCESS DETERMINATION: a job's raw exit code is NOT trusted alone.
NFL's own wrapper, by design, can exit 1 on a cycle where every
DraftGroup but one published real data (the steady state while a future
DraftGroup returns SCHEMA_CHANGED) -- a bare "exit code != 0" check would
misclassify that as a total failure. Instead, after the child process
exits (or is killed for a timeout), this script re-reads that sport's
OWN status file (the exact file the wrapper already writes on every
real run) and checks whether last_success_at advanced past the moment
THIS attempt was launched. That is the same ground truth a human
already checks, reused rather than re-derived, and it is correct for
both wrappers' real exit-code quirks without special-casing either one.

.PARAMETER Shadow
Runs against sports_registry.shadow.json (simulate_job.ps1 as every
sport's "job") instead of the real production registry. Used only for
Shadow Verification (section 10) -- never touches DraftKings, Railway,
Postgres, or R2 in this mode.

.PARAMETER RegistryPath
Override the sports registry JSON path directly. Takes precedence over
-Shadow's default selection.

.PARAMETER StatusOutputFile
Where the machine-readable orchestrator status artifact is written.
Defaults to logs\orchestrator_status.json (production) so shadow runs
should pass a distinct path to avoid any chance of confusing the two.

.PARAMETER TickIntervalSeconds
How often the main loop wakes to check due-ness / process completion /
timeouts. 15s in production is frequent enough to react to a hung job
quickly without meaningfully increasing CPU/log churn.

.PARAMETER MaxTicks
0 = run forever (production). >0 = exit after that many ticks -- used
only to bound shadow-verification test runs so they terminate on their
own rather than requiring a manual kill.
#>
param(
    [switch]$Shadow,
    [string]$RegistryPath,
    [string]$StatusOutputFile,
    [int]$TickIntervalSeconds = 15,
    [int]$MaxTicks = 0
)

$ErrorActionPreference = "Stop"

# ---- Paths ------------------------------------------------------------
$ScriptRoot = $PSScriptRoot
$RepoRoot   = Split-Path -Parent (Split-Path -Parent $ScriptRoot)   # D:\mlb-dfs-engine
$LogDir     = Join-Path $RepoRoot "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

if (-not $RegistryPath) {
    $RegistryPath = if ($Shadow) { Join-Path $ScriptRoot "sports_registry.shadow.json" } else { Join-Path $ScriptRoot "sports_registry.json" }
}
if (-not $StatusOutputFile) {
    $StatusOutputFile = Join-Path $LogDir "orchestrator_status.json"
}
$LogFile = Join-Path $LogDir "orchestrator.log"

# ---- Bounded, atomic log growth (mirrors the NFL worker's own proven
# pattern: only rewrite when oversized, staged through a temp file +
# atomic Move so a kill mid-rewrite can never destroy the log). --------
$LogMaxLines  = 5000
$LogKeepLines = 2000
function Write-OrchestratorLog([string]$Message) {
    $line = "{0} {1}" -f (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ"), $Message
    Write-Host $line
    try {
        if (Test-Path $LogFile) {
            $lineCount = (Get-Content $LogFile -ReadCount 0 | Measure-Object -Line).Lines
            if ($lineCount -gt $LogMaxLines) {
                $tmp = "$LogFile.trim.tmp"
                Get-Content $LogFile -Tail $LogKeepLines | Set-Content -Path $tmp -Encoding utf8
                Move-Item -Path $tmp -Destination $LogFile -Force
            }
        }
        Add-Content -Path $LogFile -Value $line -Encoding utf8
    } catch { }
}

# ---- Single instance: named Mutex, not Task Scheduler's own
# MultipleInstances setting -- testable independently (this is exactly
# what Test G exercises: run this script a second time by hand and
# confirm it exits immediately). WaitOne(TimeSpan.Zero) is a
# non-blocking try-acquire; an AbandonedMutexException means a previous
# instance died without releasing it (crash, kill -9, power loss) --
# treated as a successful, self-healing takeover, not an error, since a
# dead process obviously is not "the healthy existing orchestrator" the
# brief says never to kill. ----------------------------------------------
$MutexName = "Global\BigMoneyDFS_Orchestrator"
$mutex = New-Object System.Threading.Mutex($false, $MutexName)
$acquired = $false
try {
    $acquired = $mutex.WaitOne([TimeSpan]::Zero)
} catch [System.Threading.AbandonedMutexException] {
    $acquired = $true
    Write-OrchestratorLog "previous orchestrator instance's mutex was abandoned (died without cleanup) -- recovered, taking ownership"
}
if (-not $acquired) {
    Write-Host "ORCHESTRATOR_ALREADY_RUNNING"
    exit 0
}

# ---- Load the sport registry -------------------------------------------
if (-not (Test-Path $RegistryPath)) {
    Write-OrchestratorLog "FATAL: sports registry not found at $RegistryPath"
    $mutex.ReleaseMutex(); $mutex.Dispose()
    exit 1
}
$registry = Get-Content $RegistryPath -Raw | ConvertFrom-Json

$startedAtUtc = (Get-Date).ToUniversalTime()
Write-OrchestratorLog ("===== ORCHESTRATOR START mode={0} registry={1} =====" -f $(if ($Shadow) { "shadow" } else { "production" }), $RegistryPath)

# ---- Per-sport in-memory state ------------------------------------------
# All ISO timestamps are UTC 'o'-format strings (lexicographically
# sortable, matches every other status artifact in this project).
$state = @{}
foreach ($cfg in $registry) {
    $state[$cfg.sport] = [pscustomobject]@{
        Config              = $cfg
        CurrentlyRunning    = $false
        Process             = $null
        AttemptStartedAt    = $null
        LastAttempt         = $null
        LastSuccess         = $null
        LastFailure         = $null
        NextDue             = $startedAtUtc
        DurationSeconds     = $null
        ConsecutiveFailures = 0
        LastError           = $null
    }
}

function Test-JobSucceeded([string]$StatusFile, [datetime]$SinceUtc) {
    if (-not $StatusFile -or -not (Test-Path $StatusFile)) { return $false }
    try {
        $doc = Get-Content $StatusFile -Raw | ConvertFrom-Json
        if (-not $doc.last_success_at) { return $false }
        $lastSuccess = [datetime]::Parse(
            $doc.last_success_at, [System.Globalization.CultureInfo]::InvariantCulture,
            [System.Globalization.DateTimeStyles]::RoundtripKind
        ).ToUniversalTime()
        return ($lastSuccess -ge $SinceUtc)
    } catch {
        return $false
    }
}

function Get-FreshnessInfo([string]$StatusFile, [int]$ThresholdSeconds) {
    $result = [ordered]@{ freshness_age_seconds = $null; freshness_status = "AWAITING_DATA"; underlying_last_success_at = $null }
    if (-not $StatusFile -or -not (Test-Path $StatusFile)) { return $result }
    try {
        $doc = Get-Content $StatusFile -Raw | ConvertFrom-Json
        if (-not $doc.last_success_at) { return $result }
        $lastSuccess = [datetime]::Parse(
            $doc.last_success_at, [System.Globalization.CultureInfo]::InvariantCulture,
            [System.Globalization.DateTimeStyles]::RoundtripKind
        ).ToUniversalTime()
        $ageSeconds = ((Get-Date).ToUniversalTime() - $lastSuccess).TotalSeconds
        $result.freshness_age_seconds = [math]::Round($ageSeconds, 1)
        $result.freshness_status = if ($ageSeconds -le $ThresholdSeconds) { "fresh" } else { "stale" }
        $result.underlying_last_success_at = $doc.last_success_at
    } catch { }
    return $result
}

function Write-StatusArtifact {
    $sportsOut = [ordered]@{}
    foreach ($name in ($state.Keys | Sort-Object)) {
        $s = $state[$name]
        $fresh = Get-FreshnessInfo -StatusFile $s.Config.statusFile -ThresholdSeconds $s.Config.freshnessThresholdSeconds
        $sportsOut[$name] = [ordered]@{
            enabled                    = [bool]$s.Config.enabled
            currently_running          = $s.CurrentlyRunning
            last_attempt               = $s.LastAttempt
            last_success               = $s.LastSuccess
            last_failure               = $s.LastFailure
            next_due                   = $s.NextDue.ToString("o")
            duration_seconds           = $s.DurationSeconds
            consecutive_failures       = $s.ConsecutiveFailures
            freshness_age_seconds      = $fresh.freshness_age_seconds
            freshness_status           = $fresh.freshness_status
            underlying_last_success_at = $fresh.underlying_last_success_at
            last_error                 = $s.LastError
        }
    }
    $doc = [ordered]@{
        orchestrator_started_at    = $startedAtUtc.ToString("o")
        orchestrator_last_heartbeat = (Get-Date).ToUniversalTime().ToString("o")
        mode                       = $(if ($Shadow) { "shadow" } else { "production" })
        sports                     = $sportsOut
    }
    try {
        $tmp = "$StatusOutputFile.tmp"
        $doc | ConvertTo-Json -Depth 6 | Set-Content -Path $tmp -Encoding utf8
        Move-Item -Path $tmp -Destination $StatusOutputFile -Force
    } catch { }
}

function Start-SportJob($s) {
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName               = "powershell.exe"
    $extraArgs = if ($s.Config.jobArguments) { " $($s.Config.jobArguments)" } else { "" }
    $psi.Arguments              = "-NoProfile -ExecutionPolicy Bypass -File `"$($s.Config.jobScript)`"$extraArgs"
    $psi.WorkingDirectory        = $s.Config.workingDirectory
    $psi.UseShellExecute        = $false
    $psi.CreateNoWindow         = $true
    # Deliberately NOT redirecting stdout/stderr: the wrapper scripts
    # already write their own complete logs to their own log files, and
    # redirecting without a drain loop is exactly the full-pipe-buffer
    # deadlock class this project already found and fixed once this
    # session (NFL downstream stages). Not redirecting removes that
    # failure mode entirely rather than reintroducing and re-guarding it.
    $proc = New-Object System.Diagnostics.Process
    $proc.StartInfo = $psi
    [void]$proc.Start()
    return $proc
}

# ---- Main loop ----------------------------------------------------------
$tick = 0
try {
    while ($true) {
        $tick++
        $nowUtc = (Get-Date).ToUniversalTime()

        foreach ($name in $state.Keys) {
            $s = $state[$name]
            if (-not $s.Config.enabled) { continue }

            if ($s.CurrentlyRunning) {
                $proc = $s.Process
                $elapsed = ($nowUtc - $s.AttemptStartedAt).TotalSeconds

                $proc.Refresh()
                if ($proc.HasExited) {
                    $succeeded = Test-JobSucceeded -StatusFile $s.Config.statusFile -SinceUtc $s.AttemptStartedAt
                    $s.DurationSeconds = [math]::Round($elapsed, 1)
                    $s.CurrentlyRunning = $false
                    $exitCode = $null
                    try { $exitCode = $proc.ExitCode } catch { }
                    $s.Process = $null

                    if ($succeeded) {
                        $s.LastSuccess = $nowUtc.ToString("o")
                        $s.ConsecutiveFailures = 0
                        $s.LastError = $null
                        $s.NextDue = $nowUtc.AddSeconds($s.Config.refreshIntervalSeconds)
                        Write-OrchestratorLog ("SPORT={0} END result=SUCCESS duration={1}s exit={2}" -f $name, $s.DurationSeconds, $exitCode)
                    } else {
                        $s.LastFailure = $nowUtc.ToString("o")
                        $s.ConsecutiveFailures += 1
                        $s.LastError = "job exited (code $exitCode) without advancing last_success_at"
                        $retryDelay = [math]::Min($s.Config.retryIntervalSeconds * $s.ConsecutiveFailures, $s.Config.refreshIntervalSeconds)
                        $s.NextDue = $nowUtc.AddSeconds($retryDelay)
                        Write-OrchestratorLog ("SPORT={0} END result=FAILURE duration={1}s exit={2} consecutive_failures={3} retry_in={4}s" -f $name, $s.DurationSeconds, $exitCode, $s.ConsecutiveFailures, $retryDelay)
                    }
                } elseif ($elapsed -gt $s.Config.timeoutSeconds) {
                    try { & taskkill.exe /PID $proc.Id /T /F 2>&1 | Out-Null } catch { }
                    $s.DurationSeconds = [math]::Round($elapsed, 1)
                    $s.CurrentlyRunning = $false
                    $s.Process = $null
                    $s.LastFailure = $nowUtc.ToString("o")
                    $s.ConsecutiveFailures += 1
                    $s.LastError = "TIMEOUT after $($s.DurationSeconds)s (limit $($s.Config.timeoutSeconds)s) -- process tree killed"
                    $retryDelay = [math]::Min($s.Config.retryIntervalSeconds * $s.ConsecutiveFailures, $s.Config.refreshIntervalSeconds)
                    $s.NextDue = $nowUtc.AddSeconds($retryDelay)
                    Write-OrchestratorLog ("SPORT={0} END result=TIMEOUT duration={1}s consecutive_failures={2} retry_in={3}s" -f $name, $s.DurationSeconds, $s.ConsecutiveFailures, $retryDelay)
                }
                continue
            }

            if ($nowUtc -ge $s.NextDue) {
                $proc = Start-SportJob $s
                $s.Process = $proc
                $s.CurrentlyRunning = $true
                $s.AttemptStartedAt = $nowUtc
                $s.LastAttempt = $nowUtc.ToString("o")
                Write-OrchestratorLog ("SPORT={0} START pid={1}" -f $name, $proc.Id)
            }
        }

        Write-StatusArtifact

        if ($MaxTicks -gt 0 -and $tick -ge $MaxTicks) {
            Write-OrchestratorLog ("reached MaxTicks={0}, stopping (test/bounded run)" -f $MaxTicks)
            break
        }
        Start-Sleep -Seconds $TickIntervalSeconds
    }
} finally {
    # Best-effort: never leave a running job's process orphaned if the
    # orchestrator itself is stopping cleanly (Ctrl+C reaches this
    # finally under normal PowerShell script termination; an abrupt
    # kill -9 of THIS process does not, which is exactly the case the
    # Mutex's AbandonedMutexException recovery above exists for).
    foreach ($name in $state.Keys) {
        $s = $state[$name]
        if ($s.CurrentlyRunning -and $s.Process -and -not $s.Process.HasExited) {
            Write-OrchestratorLog ("orchestrator stopping -- leaving in-flight job for {0} running (not killed): it is a real, in-progress production refresh, not something to abort just because the supervisor is exiting" -f $name)
        }
    }
    Write-OrchestratorLog "===== ORCHESTRATOR STOP ====="
    try { $mutex.ReleaseMutex() } catch { }
    $mutex.Dispose()
}
