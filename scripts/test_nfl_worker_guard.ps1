# Controlled tests for run_nfl_dk_fetch_worker.ps1's MLB-active guard and
# starvation escape hatch, at the current $NflMaxPublishAgeMinutes
# threshold (20 minutes as of 2026-09-13; read from the worker script
# itself below so this test can never silently drift out of sync with
# the value it is meant to prove).
#
# No PowerShell test harness (Pester or otherwise) existed for either
# DFS worker before this file -- every prior verification in this
# project was a manual, controlled invocation of the real wrapper with
# its real status file aged to a known value, its output inspected for
# the exact log marker and exit code. This script codifies that same
# method as a reusable, versioned test rather than a one-off terminal
# session, so it can be re-run whenever the threshold changes again.
#
# It runs the REAL wrapper script end to end (never a mock of the guard
# logic in isolation) against the REAL status file and the REAL current
# state of the MLB scheduled task/processes on this machine -- the same
# process/task signals Test-MlbWorkerActive itself reads. This means:
#   - Tests A and B require MLB to actually be in the state they assert
#     (active / idle) at run time. The script detects which state is
#     currently true and reports that test's applicability rather than
#     asserting a false precondition.
#   - The status file is backed up before any test writes to it and is
#     ALWAYS restored in a finally block, so running this script never
#     leaves the real worker's state corrupted.
#
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test_nfl_worker_guard.ps1

$ErrorActionPreference = "Stop"
$repoRoot   = Split-Path -Parent $PSScriptRoot
$workerPath = Join-Path $repoRoot "scripts\run_nfl_dk_fetch_worker.ps1"
$logDir     = Join-Path $repoRoot "logs"
$logPath    = Join-Path $logDir "nfl_dk_fetch_worker.log"
$statusPath = Join-Path $logDir "nfl_dk_fetch_worker_status.json"

if (-not (Test-Path $workerPath)) { throw "worker script not found at $workerPath" }

# Read the threshold straight from the script under test -- this assertion
# fails loudly if a future edit changes the constant without updating
# this test's own expectations.
$scriptText = Get-Content $workerPath -Raw
if ($scriptText -notmatch '\$NflMaxPublishAgeMinutes\s*=\s*(\d+)') {
    throw "could not find `$NflMaxPublishAgeMinutes in $workerPath"
}
$threshold = [int]$Matches[1]
Write-Host "Testing against `$NflMaxPublishAgeMinutes = $threshold (read from the worker script itself)"

function Test-MlbWorkerActiveNow {
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

function Set-StatusAge([int]$minutesAgo) {
    $ts = (Get-Date).ToUniversalTime().AddMinutes(-$minutesAgo).ToString("o")
    $doc = [ordered]@{
        last_run_at     = $ts
        last_outcome    = "published"
        last_exit_code  = 1
        forced_refresh  = $false
        last_success_at = $ts
    }
    $doc | ConvertTo-Json | Set-Content -Path $statusPath -Encoding utf8
}

function Get-LogTail([int]$sinceLineCount = 12) {
    if (-not (Test-Path $logPath)) { return @() }
    Get-Content $logPath -Tail $sinceLineCount
}

function Invoke-WorkerAndCapture([int]$timeoutSeconds = 30) {
    $before = 0
    if (Test-Path $logPath) { $before = (Get-Content $logPath).Count }
    $proc = Start-Process -FilePath "powershell.exe" `
        -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$workerPath`"" `
        -PassThru -WindowStyle Hidden
    $exited = $proc.WaitForExit($timeoutSeconds * 1000)
    $exitCode = $null
    if ($exited) {
        $exitCode = $proc.ExitCode
    } else {
        # Only relevant if a forced refresh actually reaches the real
        # (slow) fetch; the deferred path exits in ~1s. Kill the tree
        # rather than leave an orphan behind from this test itself.
        & taskkill.exe /PID $proc.Id /T /F 2>&1 | Out-Null
    }
    $after = 0
    if (Test-Path $logPath) { $after = (Get-Content $logPath).Count }
    $newLines = @()
    if ((Test-Path $logPath) -and ($after -gt $before)) {
        $newLines = Get-Content $logPath | Select-Object -Skip $before
    }
    [pscustomobject]@{ Exited = $exited; ExitCode = $exitCode; NewLines = $newLines }
}

function Get-RailwayNflProcessCount {
    @(Get-CimInstance Win32_Process -Filter "Name='railway.exe' OR Name='node.exe'" -ErrorAction SilentlyContinue |
      Where-Object { $_.CommandLine -and $_.CommandLine -match 'nfl-web' }).Count
}

$results = @()
function Record([string]$name, [bool]$pass, [string]$detail) {
    $script:results += [pscustomobject]@{ Test = $name; Pass = $pass; Detail = $detail }
    $mark = if ($pass) { "PASS" } else { "FAIL" }
    Write-Host ("[{0}] {1}: {2}" -f $mark, $name, $detail)
}

$statusBackup = $null
if (Test-Path $statusPath) { $statusBackup = Get-Content $statusPath -Raw }

try {
    $mlbActiveAtStart = Test-MlbWorkerActiveNow
    Write-Host "MLB worker active at test start: $mlbActiveAtStart`n"

    # ---- Test A: age < threshold + MLB active -> defer -------------------
    if ($mlbActiveAtStart) {
        Set-StatusAge ([int]($threshold / 2))
        $before = Get-RailwayNflProcessCount
        $r = Invoke-WorkerAndCapture -timeoutSeconds 15
        $after = Get-RailwayNflProcessCount
        $deferred = ($r.NewLines -join "`n") -match "NFL_DEFERRED_MLB_ACTIVE"
        $noProcs = ($after -eq $before)
        Record "A: age<${threshold}min + MLB active -> defer" `
            ($deferred -and $noProcs -and $r.Exited -and $r.ExitCode -eq 0) `
            "exited=$($r.Exited) exitCode=$($r.ExitCode) deferred_marker=$deferred railway_procs_before=$before after=$after"

        # Checked HERE, immediately, before Test B's forced refresh can
        # legitimately overwrite this same status file with a real
        # "published" outcome -- checking it later would validate Test
        # B's result under Test A's name.
        if (Test-Path $statusPath) {
            $statusAfterA = Get-Content $statusPath -Raw | ConvertFrom-Json
            Record "No fake success on defer" ($statusAfterA.last_outcome -eq "deferred_mlb_active") `
                "status.last_outcome=$($statusAfterA.last_outcome) (must be deferred_mlb_active, never 'published')"
        }
    } else {
        Record "A: age<${threshold}min + MLB active -> defer" $true "SKIPPED (MLB not active at test time -- see Test C for the idle path)"
        Record "No fake success on defer" $true "SKIPPED (depends on Test A, which did not run)"
    }

    # ---- Test B: age >= threshold + MLB active -> forced refresh ---------
    if ($mlbActiveAtStart) {
        Set-StatusAge ($threshold + 5)
        $r = Invoke-WorkerAndCapture -timeoutSeconds 300
        $forced = ($r.NewLines -join "`n") -match "NFL_FORCED_REFRESH_AGE_LIMIT"
        $deferredAlso = ($r.NewLines -join "`n") -match "NFL_DEFERRED_MLB_ACTIVE"
        Record "B: age>=${threshold}min + MLB active -> forced refresh" `
            ($forced -and -not $deferredAlso) `
            "forced_marker=$forced deferred_marker_absent=$(-not $deferredAlso) exitCode=$($r.ExitCode)"
    } else {
        Record "B: age>=${threshold}min + MLB active -> forced refresh" $true "SKIPPED (MLB not active at test time)"
    }

    # ---- Test C: MLB idle -> normal refresh, no guard interference -------
    if (-not $mlbActiveAtStart) {
        Set-StatusAge ([int]($threshold / 2))  # would defer if MLB were active
        $r = Invoke-WorkerAndCapture -timeoutSeconds 300
        $deferred = ($r.NewLines -join "`n") -match "NFL_DEFERRED_MLB_ACTIVE"
        $forced = ($r.NewLines -join "`n") -match "NFL_FORCED_REFRESH_AGE_LIMIT"
        Record "C: MLB idle -> normal refresh" `
            (-not $deferred -and -not $forced) `
            "neither guard marker fired (deferred=$deferred forced=$forced), exitCode=$($r.ExitCode)"
    } else {
        Record "C: MLB idle -> normal refresh" $true "SKIPPED (MLB was active for the whole test run -- see Test A/B)"
    }

    # ---- No orphan processes after all tests ------------------------------
    Start-Sleep -Seconds 3
    $orphans = Get-RailwayNflProcessCount
    Record "No orphan processes after tests" ($orphans -eq 0) "railway/node procs referencing nfl-web still running: $orphans"

} finally {
    if ($statusBackup) {
        Set-Content -Path $statusPath -Value $statusBackup -Encoding utf8
    } elseif (Test-Path $statusPath) {
        Remove-Item $statusPath -Force
    }
    Write-Host "`nstatus file restored to its pre-test state"
}

Write-Host "`n===== SUMMARY ====="
$results | ForEach-Object { "{0} {1}: {2}" -f ($(if($_.Pass){"PASS"}else{"FAIL"}), $_.Test, $_.Detail) }
$failed = @($results | Where-Object { -not $_.Pass })
if ($failed.Count -gt 0) {
    Write-Host "`n$($failed.Count) test(s) FAILED"
    exit 1
} else {
    Write-Host "`nAll applicable tests passed."
    exit 0
}
