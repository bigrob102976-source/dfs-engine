# TEST-ONLY. Never invoked in production mode -- run_orchestrator.ps1 only
# calls this when started with -Shadow, and only against the shadow sports
# registry (sports_registry.shadow.json), which points every sport's
# jobScript at this file instead of the real MLB/NFL wrapper scripts.
#
# Exists so orchestrator scheduling/concurrency/timeout/retry logic can be
# proven correct (Shadow Verification, section 10 of the implementation
# brief) without ever touching real DraftKings/Railway/Postgres/R2
# production systems, and without needing the real pipelines to
# cooperate with an artificially injected hang or failure.
#
# Behavior is read from a small per-sport control file
# (shadow_control\<Sport>.json) that a TEST can rewrite between
# orchestrator ticks to switch scenarios live against one running
# orchestrator instance, e.g.:
#   { "behavior": "succeed", "durationSeconds": 5 }
#   { "behavior": "hang" }
#   { "behavior": "fail", "durationSeconds": 3 }
# Missing/unreadable control file defaults to a quick, clean success --
# a fresh shadow run with no setup exercises the normal healthy case.
#
# "Succeed" writes a status file in the SAME shape/field names as the
# real MLB/NFL wrapper status JSON (last_run_at, last_success_at,
# consecutive_failures) so run_orchestrator.ps1's real
# "did the status file's last_success_at advance" success check -- the
# same logic it will use against the real wrappers -- gets exercised
# here too, not a separate code path.

param(
    [Parameter(Mandatory = $true)][string]$Sport,
    [Parameter(Mandatory = $true)][string]$StatusFile
)

$ErrorActionPreference = "Stop"
$controlDir = Join-Path $PSScriptRoot "shadow_control"
New-Item -ItemType Directory -Force -Path $controlDir | Out-Null
$controlFile = Join-Path $controlDir "$Sport.json"

$behavior = "succeed"
$durationSeconds = 5
if (Test-Path $controlFile) {
    try {
        $control = Get-Content $controlFile -Raw | ConvertFrom-Json
        if ($control.behavior) { $behavior = $control.behavior }
        if ($control.durationSeconds) { $durationSeconds = [int]$control.durationSeconds }
    } catch { }
}

Write-Host "[simulate_job] sport=$Sport behavior=$behavior durationSeconds=$durationSeconds"

function Write-StatusFile([string]$outcome, [int]$consecutiveFailures) {
    $nowIso = (Get-Date).ToUniversalTime().ToString("o")
    $prior = $null
    if (Test-Path $StatusFile) {
        try { $prior = Get-Content $StatusFile -Raw | ConvertFrom-Json } catch { $prior = $null }
    }
    $lastSuccessAt = if ($outcome -eq "success") { $nowIso } elseif ($prior) { $prior.last_success_at } else { $null }
    $doc = [ordered]@{
        worker_id           = "SIMULATED_$Sport"
        last_run_at         = $nowIso
        success             = ($outcome -eq "success")
        last_success_at     = $lastSuccessAt
        consecutive_failures = $consecutiveFailures
    }
    $statusDir = Split-Path -Parent $StatusFile
    New-Item -ItemType Directory -Force -Path $statusDir | Out-Null
    $doc | ConvertTo-Json | Set-Content -Path $StatusFile -Encoding utf8
}

switch ($behavior) {
    "hang" {
        # Never returns on its own -- the orchestrator's own timeout must
        # kill this process tree. Sleeps in short increments so a
        # taskkill/Ctrl+C actually interrupts it promptly rather than
        # blocking in one long Start-Sleep.
        while ($true) { Start-Sleep -Seconds 2 }
    }
    "fail" {
        Start-Sleep -Seconds $durationSeconds
        $prior = if (Test-Path $StatusFile) { try { Get-Content $StatusFile -Raw | ConvertFrom-Json } catch { $null } } else { $null }
        $priorFailures = if ($prior -and $prior.consecutive_failures) { [int]$prior.consecutive_failures } else { 0 }
        Write-StatusFile -outcome "failure" -consecutiveFailures ($priorFailures + 1)
        Write-Host "[simulate_job] sport=$Sport simulated FAILURE"
        exit 1
    }
    default {
        Start-Sleep -Seconds $durationSeconds
        Write-StatusFile -outcome "success" -consecutiveFailures 0
        Write-Host "[simulate_job] sport=$Sport simulated SUCCESS"
        exit 0
    }
}
