# BigMoneyDFS_MLB_DK_Fetch_Worker's scheduled-task action.
#
# Recreated on THIS collector machine (user `taylo`, repo on D:) after the
# previous MLB worker was found dead: its hardcoded paths all pointed at
# C:\Users\bigro\mlb-dfs-engine on a machine/profile that no longer
# exists here, so every MLB data type (DK slate, research, identity,
# Native projections, ownership, Vegas/environment) silently stopped
# refreshing on 2026-09-08 ~21:30-21:50 UTC with no alerting.
#
# Mirrors the proven NFL worker (scripts/run_nfl_dk_fetch_worker.ps1)
# for process/paths, and preserves the ORIGINAL MLB worker's hard-won
# fixes, which are deliberately kept:
#   * an INTERNAL timeout shorter than Task Scheduler's ExecutionTimeLimit,
#     so this script always gets to log/record a hang itself rather than
#     being hard-killed with no trace (the original failure mode that made
#     past outages undiagnosable);
#   * output redirected to the log file as the child produces it, so a
#     killed run's output survives;
#   * a status JSON + CRITICAL_ALERT file so "is something wrong right
#     now" is answerable without reading logs;
#   * America/Chicago date anchoring, matching the app's own slate-date
#     convention (dashboard/lib/currentDate.ts) so a run near the UTC day
#     boundary never fetches the wrong calendar date.
#
# Two stages, matching the original pipeline exactly:
#   1. DK fetch  (every run)  -- railway run  -- real DraftKings network
#      access lives on this machine; Railway's egress is IP-blocked by DK.
#   2. research/identity/eligibility/projections/ownership (~every 10 min)
#      -- railway ssh -- needs the container's INTERNAL Postgres network,
#      which `railway run` (which executes locally) cannot reach.
#
# Never writes mock/synthetic/CSV data: both stages call the app's own
# already-tested production scripts unchanged.

$RepoRoot   = "D:\mlb-dfs-engine"
$NpxPath    = "C:\Users\taylo\AppData\Local\Programs\nodejs\npx.cmd"
# Passed explicitly to every Railway call: the CLI's project link is
# per-directory state, and this repo root is deliberately NOT linked
# (the first run failed with "No linked project found"). An explicit
# --project makes the worker independent of local CLI link state, so it
# can never silently break because someone re-linked a directory.
$RailwayProjectId = "3f0a4e42-22a4-4ebd-8e7f-2006261c5393"
# mlb-dfs-engine has no venv of its own; the sibling worktree's venv has
# the real production deps (boto3/pandas/scikit-learn/ortools) and is used
# purely as an interpreter -- cwd below is always $RepoRoot.
$VenvPython = "D:\nfl-dfs-engine\.venv\Scripts\python.exe"

$LogDir            = Join-Path $RepoRoot "logs"
$LogFile           = Join-Path $LogDir "mlb_dk_fetch_worker.log"
$StatusFile        = Join-Path $LogDir "mlb_dk_fetch_worker_status.json"
$CriticalAlertFile = Join-Path $LogDir "MLB_CRITICAL_ALERT.txt"

$InternalTimeoutSeconds           = 240
$ResearchRefreshIntervalMinutes   = 10
# The research stage is an 8-step pipeline (research -> identity ->
# eligibility -> pitcher agent -> batter agent -> Native projections ->
# ownership -> canonical promotion). Measured live on 2026-09-09: steps
# 1-4 alone take ~78s (pitcher agent 55.6s), and the original 180s limit
# killed it mid batter-agent (step 5/8) every cycle. 600s gives the full
# pipeline real headroom; Task Scheduler's ExecutionTimeLimit is set
# above the sum of both stages so neither is ever hard-killed externally.
$ResearchInternalTimeoutSeconds   = 600
$CriticalAlertThreshold           = 3

# Stage-budget accounting (2026-09-12). Task Scheduler's own
# ExecutionTimeLimit for BigMoneyDFS_MLB_DK_Fetch_Worker is PT15M, and the
# three stages share it: DK fetch (<=240s) + research (<=600s) + Vegas/
# weather (<=240s) sums to 1080s, MORE than the 900s outer limit. The
# original guard protected that limit with a fixed "$dkSeconds -lt 100"
# test, but $dkSeconds is the WALL time of the whole `npx @railway/cli
# run` invocation -- CLI resolution plus production env fetch alone is
# ~45-60s on top of the fetch script's own ~60-65s -- so the DK stage has
# not come in under 100s in normal operation since the two-date prefetch
# landed. The guard therefore fired EVERY cycle and starved the research
# stage indefinitely (projections/ownership last refreshed 2026-09-12
# 04:47Z, ~22h stale, and absent entirely for the next slate date).
# Replaced with a real remaining-budget check: research now gets whatever
# time is actually left after the DK stage, capped at its own limit and
# floored at the point where it could not finish anyway. This keeps the
# original intent (never overrun the outer limit) without ever starving.
$OuterExecutionLimitSeconds        = 900
$EnvironmentStageReserveSeconds    = 240
$StatusWriteReserveSeconds         = 30
# Steps 1-4 of the 8-step pipeline alone measured ~78s on 2026-09-09, so a
# budget below this cannot reach the projection/ownership steps that are
# the whole point of the stage -- skipping is honest, a doomed run is not.
$ResearchMinimumUsefulSeconds      = 150

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
if (-not (Test-Path $LogFile)) { New-Item -ItemType File -Path $LogFile | Out-Null }

# Bound log growth -- keep the most recent ~3000 lines.
$existing = Get-Content $LogFile -Tail 3000 -ErrorAction SilentlyContinue
if ($existing) { Set-Content -Path $LogFile -Value $existing -Encoding utf8 }

function Write-Log([string]$Line) { Add-Content -Path $LogFile -Value $Line -Encoding utf8 }

# DIAGNOSTIC HARDENING (2026-09-10): the research/identity/projections/
# ownership stage has been observed dying with exit code 3221225786
# (0xC000013A / STATUS_CONTROL_C_EXIT) shortly after starting, with
# NOTHING logged beyond the stage's own "starting" line -- no exception,
# no stack trace, nothing to diagnose from. STATUS_CONTROL_C_EXIT is the
# code Windows assigns a console process killed by an external signal
# (Ctrl+C/logoff/console-close) OR, in some PowerShell/.NET version
# combinations, by an UNHANDLED exception thrown inside a
# Register-ObjectEvent -Action scriptblock (used below for streaming a
# child process's stdout/stderr) -- that class of error runs in its own
# background runspace and can destabilize the whole host if it escapes
# uncaught. This script-level trap cannot catch a genuine external kill
# (the whole process is gone before any PowerShell code could run), but
# it DOES catch the second case, and its mere presence going forward
# lets a future incident say definitively "the process was killed
# externally, since this trap did NOT fire" rather than leaving that
# ambiguous. Exits with the distinct sentinel code 66 (never
# 3221225786) so Task Scheduler's LastTaskResult itself distinguishes
# "we caught and logged this" from "something else killed us."
trap {
    Write-Log "!!! UNCAUGHT EXCEPTION (script-level trap) !!!"
    Write-Log "Type    : $($_.Exception.GetType().FullName)"
    Write-Log "Message : $($_.Exception.Message)"
    Write-Log "At      : $($_.InvocationInfo.PositionMessage)"
    Write-Log "Stack   : $($_.ScriptStackTrace)"
    if ($_.Exception.InnerException) {
        Write-Log "Inner   : $($_.Exception.InnerException.GetType().FullName): $($_.Exception.InnerException.Message)"
    }
    exit 66
}

$ChicagoTz  = [System.TimeZoneInfo]::FindSystemTimeZoneById("Central Standard Time")
$ChicagoNow = [System.TimeZoneInfo]::ConvertTimeFromUtc((Get-Date).ToUniversalTime(), $ChicagoTz)
$Date       = $ChicagoNow.ToString("yyyy-MM-dd")

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

$StartedAtUtc = (Get-Date).ToUniversalTime()
$StartedAt = $StartedAtUtc.ToString("o")
Write-Log "`n===== START $StartedAt -- MLB slates for $Date ====="

# Load prior status (for the research-stage gate and failure counting).
$prior = $null
if (Test-Path $StatusFile) {
    try { $prior = Get-Content $StatusFile -Raw | ConvertFrom-Json } catch { $prior = $null }
}

function Invoke-Stage {
    param([string]$Label, [string]$Arguments, [int]$TimeoutSeconds)

    Write-Log "----- $Label : starting (timeout ${TimeoutSeconds}s) -----"
    $proc    = $null
    $outEvt  = $null
    $errEvt  = $null
    $timedOut = $false
    $code     = 1
    $exceptionMessage = $null

    # DIAGNOSTIC HARDENING (2026-09-10): everything from process creation
    # through WaitForExit is now inside try/finally. Previously an
    # exception here (e.g. Register-ObjectEvent or $proc.Start() itself
    # throwing) would propagate uncaught out of this function with NO
    # log line beyond "starting" -- exactly the blind spot behind the
    # unexplained 3221225786 exits -- and would also skip
    # Unregister-Event/Dispose below, leaking a stray event subscription
    # into the NEXT cycle's runspace on every occurrence. The finally
    # block now runs that cleanup unconditionally.
    try {
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName               = $NpxPath
        $psi.Arguments              = $Arguments
        $psi.WorkingDirectory       = $RepoRoot
        $psi.UseShellExecute        = $false
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError  = $true

        $proc = New-Object System.Diagnostics.Process
        $proc.StartInfo = $psi
        # Stream output to the log AS IT ARRIVES, so a killed run's real
        # output up to the hang survives (the original worker's blind
        # spot). MessageData carries the log path in: a
        # Register-ObjectEvent action block runs in its own runspace and
        # cannot see $script:/$using: variables (the first version of
        # this worker logged nothing at all because of exactly that). An
        # exception INSIDE this scriptblock happens in that same
        # background runspace, where PowerShell's own handling has been
        # known (depending on host/version) to escalate to killing the
        # process rather than surfacing a normal error here -- so it
        # logs defensively (its own try/catch) instead of letting
        # Add-Content itself be a second point of failure.
        $onData = {
            try {
                if ($EventArgs.Data) {
                    Add-Content -Path $Event.MessageData -Value $EventArgs.Data -Encoding utf8
                }
            } catch {
                # Swallowed deliberately: this runs in a background
                # runspace on every line of child output, so it must
                # never be the thing that brings the host down. Nothing
                # meaningful to log the exception TO if Add-Content
                # itself is what's failing.
            }
        }
        $outEvt = Register-ObjectEvent -InputObject $proc -EventName OutputDataReceived -Action $onData -MessageData $LogFile
        $errEvt = Register-ObjectEvent -InputObject $proc -EventName ErrorDataReceived  -Action $onData -MessageData $LogFile

        [void]$proc.Start()
        $proc.BeginOutputReadLine()
        $proc.BeginErrorReadLine()

        if (-not $proc.WaitForExit($TimeoutSeconds * 1000)) {
            $timedOut = $true
            Write-Log "!!! $Label : INTERNAL TIMEOUT after ${TimeoutSeconds}s -- killing process tree (PID $($proc.Id)) !!!"
            try { taskkill /PID $proc.Id /T /F 2>&1 | Out-Null } catch {}
            try { $proc.WaitForExit(10000) | Out-Null } catch {}
        }

        if (-not $timedOut) { try { $code = $proc.ExitCode } catch { $code = 1 } }
    } catch {
        # Full exception detail -- message, type, inner exception, and
        # the PowerShell stack trace -- so the NEXT occurrence leaves a
        # real diagnostic trail instead of just an exit code. This is
        # the try/catch this stage was missing.
        $exceptionMessage = $_.Exception.Message
        Write-Log "!!! $Label : EXCEPTION during stage execution !!!"
        Write-Log "Type    : $($_.Exception.GetType().FullName)"
        Write-Log "Message : $exceptionMessage"
        Write-Log "At      : $($_.InvocationInfo.PositionMessage)"
        Write-Log "Stack   : $($_.ScriptStackTrace)"
        if ($_.Exception.InnerException) {
            Write-Log "Inner   : $($_.Exception.InnerException.GetType().FullName): $($_.Exception.InnerException.Message)"
        }
        $code = -1
    } finally {
        if ($outEvt) { Unregister-Event -SourceIdentifier $outEvt.Name -ErrorAction SilentlyContinue }
        if ($errEvt) { Unregister-Event -SourceIdentifier $errEvt.Name -ErrorAction SilentlyContinue }
        if ($proc)   { $proc.Dispose() }
    }

    Write-Log "----- $Label : finished exit=$code timedOut=$timedOut -----"
    return [pscustomobject]@{ ExitCode = $code; TimedOut = $timedOut; Exception = $exceptionMessage }
}

# ---- Stage 1: DK slate/salary fetch (every run) ----------------------
$dkStart = Get-Date
$dk = Invoke-Stage -Label "DK fetch" -TimeoutSeconds $InternalTimeoutSeconds `
    -Arguments "--yes @railway/cli run --project $RailwayProjectId --service dfs-engine --environment production -- `"$VenvPython`" -u scripts/fetch_all_dfs_slates.py --date $Date"
$dkSeconds = [math]::Round(((Get-Date) - $dkStart).TotalSeconds, 1)

# ---- Stage 2: research / identity / projections / ownership ----------
# Gated to ~10 minutes: MLB lineups/rosters don't change every 5 minutes,
# and this stage is genuinely more expensive (MLB Stats API + Native
# projection inference + ownership). Skipped when the DK stage was slow,
# so two slow stages never compound against one outer time limit.
$researchRan       = $false
$researchExit      = $null
$researchException = $null
$researchSkipped   = "not due"
$lastResearchAt    = $null
if ($prior -and $prior.last_research_refresh_at) { $lastResearchAt = [datetime]::Parse($prior.last_research_refresh_at).ToUniversalTime() }

$researchDue = (-not $lastResearchAt) -or (((Get-Date).ToUniversalTime() - $lastResearchAt).TotalMinutes -ge $ResearchRefreshIntervalMinutes)

# How much of the outer ExecutionTimeLimit is actually left for research,
# after what this cycle has already spent and what stage 3 still needs.
$elapsedSeconds  = ((Get-Date).ToUniversalTime() - $StartedAtUtc).TotalSeconds
$researchBudget  = [int]($OuterExecutionLimitSeconds - $elapsedSeconds - $EnvironmentStageReserveSeconds - $StatusWriteReserveSeconds)
if ($researchBudget -gt $ResearchInternalTimeoutSeconds) { $researchBudget = $ResearchInternalTimeoutSeconds }
$researchHasBudget = ($researchBudget -ge $ResearchMinimumUsefulSeconds)
Write-Log ("----- research budget: {0}s remaining of PT15M after {1}s elapsed (DK stage {2}s); minimum useful {3}s -----" -f $researchBudget, [int]$elapsedSeconds, $dkSeconds, $ResearchMinimumUsefulSeconds)

if ($researchDue -and $researchHasBudget -and (-not $dk.TimedOut)) {
    # DIAGNOSTIC HARDENING (2026-09-10): this stage has been observed
    # exiting 3221225786 (STATUS_CONTROL_C_EXIT) with nothing logged
    # beyond "starting" -- Invoke-Stage itself now catches and logs any
    # PowerShell-level exception internally (see its own comment), but
    # this call site gets its own explicit try/catch too, exactly as a
    # second, independent safety net: if a future change to Invoke-Stage
    # ever reintroduces a path that throws past its own try/catch, THIS
    # one still catches it here rather than letting it escape to the
    # script-level trap (which exits the whole cycle immediately,
    # skipping stage 3 and the status-file write below).
    try {
        $r = Invoke-Stage -Label "research/identity/projections/ownership" -TimeoutSeconds $researchBudget `
            -Arguments "--yes @railway/cli ssh --project $RailwayProjectId --service dfs-engine --environment production -- npx tsx scripts/refresh-research-and-eligibility.ts --date $Date"
        $researchRan  = $true
        $researchExit = $r.ExitCode
        $researchException = $r.Exception
        if ($r.ExitCode -eq 0) { $lastResearchAt = (Get-Date).ToUniversalTime() }
        $researchSkipped = $null
    } catch {
        $researchRan       = $true
        $researchExit      = -1
        $researchException = $_.Exception.Message
        $researchSkipped   = $null
        Write-Log "!!! research stage : EXCEPTION escaped Invoke-Stage's own try/catch (see above) !!!"
        Write-Log "Type    : $($_.Exception.GetType().FullName)"
        Write-Log "Message : $($_.Exception.Message)"
        Write-Log "Stack   : $($_.ScriptStackTrace)"
    }
} elseif (-not $researchDue) {
    $researchSkipped = "not due (every ${ResearchRefreshIntervalMinutes}m)"
    Write-Log "----- research stage skipped -- $researchSkipped -----"
} else {
    $researchSkipped = "only ${researchBudget}s of the PT15M cycle budget left after a ${dkSeconds}s DK stage (need >=${ResearchMinimumUsefulSeconds}s) or DK timed out -- retry next cycle"
    Write-Log "----- research stage skipped -- $researchSkipped -----"
}

# ---- Stage 3: Vegas / weather / game environment ---------------------
# scripts/build_game_environment_report.py (SportsGameOdds + the existing
# weather/park provider) is NOT part of the 8-step research pipeline --
# it was a separate job on the old machine and was the single data type
# still going stale after the other stages were restored. Runs on the
# same ~10-minute gate as research: Vegas lines and weather move on that
# order, and this is a cheap stage (no model inference). Uses `railway
# run` (needs R2 + provider credentials, not the internal Postgres net).
$environmentRan   = $false
$environmentExit  = $null
if ($researchDue -and (-not $dk.TimedOut)) {
    $e = Invoke-Stage -Label "vegas/weather/environment" -TimeoutSeconds 240 `
        -Arguments "--yes @railway/cli run --project $RailwayProjectId --service dfs-engine --environment production -- `"$VenvPython`" -u scripts/build_game_environment_report.py --date $Date"
    $environmentRan  = $true
    $environmentExit = $e.ExitCode
} else {
    Write-Log "----- vegas/weather/environment stage skipped (same ~${ResearchRefreshIntervalMinutes}m gate as research) -----"
}

# ---- Status / alerting ----------------------------------------------
# "No Classic slate for TODAY" is a real, expected end-of-day state, not
# a failure: late at night DraftKings often has only Showdown/Captain
# DraftGroups left for the current date, which fetch_all_dfs_slates.py
# correctly rejects via structural validation. Treating that as a hard
# failure would fire the CRITICAL alert every night and mask genuine
# outages. Tomorrow's prefetch (the valuable work at that hour) runs in
# the same stage and is unaffected.
$dkNoClassicSlateToday = $false
if ($dk.ExitCode -ne 0 -and -not $dk.TimedOut) {
    $recent = Get-Content $LogFile -Tail 80 -ErrorAction SilentlyContinue
    if ($recent -match 'not a Classic Salary Cap slate' -or $recent -match 'no DFS provider configured') {
        $dkNoClassicSlateToday = $true
        Write-Log "----- DK fetch: no Classic slate available for $Date (Showdown-only / none posted) -- treated as an expected state, not a failure -----"
    }
}
$dkOk = ($dk.ExitCode -eq 0) -or $dkNoClassicSlateToday
$success = $dkOk -and (-not $dk.TimedOut) `
    -and (($researchExit -eq $null) -or ($researchExit -eq 0)) `
    -and (($environmentExit -eq $null) -or ($environmentExit -eq 0))
$consecutiveFailures = 0
if ($prior -and $prior.consecutive_failures) { $consecutiveFailures = [int]$prior.consecutive_failures }
if ($success) { $consecutiveFailures = 0 } else { $consecutiveFailures++ }

$FinishedAt = (Get-Date).ToUniversalTime().ToString("o")
$status = [ordered]@{
    worker_id                  = "BigMoneyDFS_MLB_DK_Fetch_Worker"
    machine                    = $env:COMPUTERNAME
    slate_date                 = $Date
    started_at                 = $StartedAt
    finished_at                = $FinishedAt
    success                    = $success
    dk_exit_code               = $dk.ExitCode
    dk_timed_out               = $dk.TimedOut
    dk_seconds                 = $dkSeconds
    dk_no_classic_slate_today  = $dkNoClassicSlateToday
    research_ran               = $researchRan
    research_exit_code         = $researchExit
    research_exception         = $researchException
    research_skipped_reason    = $researchSkipped
    environment_ran            = $environmentRan
    environment_exit_code      = $environmentExit
    last_research_refresh_at   = if ($lastResearchAt) { $lastResearchAt.ToString("o") } else { $null }
    last_success_at            = if ($success) { $FinishedAt } elseif ($prior) { $prior.last_success_at } else { $null }
    consecutive_failures       = $consecutiveFailures
}
$status | ConvertTo-Json -Depth 4 | Set-Content -Path $StatusFile -Encoding utf8

if ($consecutiveFailures -ge $CriticalAlertThreshold) {
    Set-Content -Path $CriticalAlertFile -Encoding utf8 -Value @"
MLB WORKER FAILING
consecutive_failures: $consecutiveFailures
last_success_at:      $($status.last_success_at)
as_of:                $FinishedAt
See: $LogFile
"@
} elseif ($success -and (Test-Path $CriticalAlertFile)) {
    Remove-Item $CriticalAlertFile -Force -ErrorAction SilentlyContinue
}

Write-Log "===== END $FinishedAt success=$success consecutive_failures=$consecutiveFailures ====="
if ($success) { exit 0 } else { exit 1 }
